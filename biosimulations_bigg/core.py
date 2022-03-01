from Bio import Entrez
from biosimulators_utils.combine.data_model import CombineArchive, CombineArchiveContent, CombineArchiveContentFormat
from biosimulators_utils.combine.io import CombineArchiveWriter
from biosimulators_utils.config import Config
from biosimulators_utils.omex_meta.data_model import BIOSIMULATIONS_ROOT_URI_FORMAT, OmexMetadataOutputFormat
from biosimulators_utils.omex_meta.io import BiosimulationsOmexMetaWriter, BiosimulationsOmexMetaReader
# from biosimulators_utils.omex_meta.utils import build_omex_meta_file_for_model
from biosimulators_utils.ref.data_model import Reference, JournalArticle, PubMedCentralOpenAccesGraphic  # noqa: F401
from biosimulators_utils.ref.utils import get_reference, get_pubmed_central_open_access_graphics
from biosimulators_utils.sedml.data_model import (
    SedDocument, Model, ModelLanguage, SteadyStateSimulation,
    Task, DataGenerator, Report, DataSet)
from biosimulators_utils.sedml.io import SedmlSimulationWriter
from biosimulators_utils.sedml.model_utils import get_parameters_variables_outputs_for_simulation
from biosimulators_utils.viz.vega.escher import escher_to_vega
from biosimulators_utils.warnings import BioSimulatorsWarning
from unittest import mock
import biosimulators_cobrapy
import biosimulators_utils.biosimulations.utils
import boto3
import copy
import dataclasses
import datetime
import dateutil.parser
import dotenv
import os
import re
import shutil
import time
import warnings
import yaml

env = {
    **dotenv.dotenv_values("config.env"),
    **os.environ,
}

Entrez.email = env.get('ENTREZ_EMAIL', None)

__all__ = ['import_projects']


def get_models(config):
    """ Get a list of the models in the source database

    Args:
        config (:obj:`dict`): configuration

    Returns:
        :obj:`list` of :obj:`dict`: models
    """
    response = config['source_session'].get(config['source_api_endpoint'] + '/models')
    response.raise_for_status()
    models = response.json()['results']
    models.sort(key=lambda model: model['bigg_id'])
    return models


def get_model_details(model, last_updated, config):
    """ Get the details of a model from the source database and download the associated files

    Args:
        model (:obj:`dict`): model
        last_updated (:obj:`datetime.datetime`): timestamp when the model was last updated
        config (:obj:`dict`): configuration

    Returns:
        :obj:`dict`: detailed information about the model
    """
    # get information about the model
    response = config['source_session'].get(config['source_api_endpoint'] + '/models/' + model['bigg_id'])
    response.raise_for_status()
    model_detail = response.json()

    download_files = (
        last_updated is None
        or config['update_project_sources']
        or (dateutil.parser.parse(model_detail['last_updated']) + datetime.timedelta(1)) > last_updated
    )

    if download_files:
        # download the file for the model
        model_filename = os.path.join(config['source_models_dirname'], model['bigg_id'] + '.xml')
        response = config['source_session'].get(config['source_model_file_endpoint'] + '/models/{}.xml'.format(model['bigg_id']))
        response.raise_for_status()
        with open(model_filename, 'wb') as file:
            file.write(response.content)

        # download flux map visualizations associated with the model
        for escher_map in model_detail['escher_maps']:
            map_name = escher_map['map_name']
            standardized_map_name = re.sub(r'[^a-zA-Z0-9\.]', '-', map_name)
            escher_filename = os.path.join(config['source_visualizations_dirname'], standardized_map_name + '.json')
            response = config['source_session'].get(config['source_map_file_endpoint'] + '/' + map_name)
            response.raise_for_status()
            with open(escher_filename, 'wb') as file:
                file.write(response.content)

    # return the details of the model
    return model_detail


def get_metadata_for_model(model_detail, config):
    """ Get additional metadata about a model

    * NCBI Taxonomy id of the organism
    * PubMed id, PubMed Central id and DOI for the reference
    * Open access figures for the reference

    Args:
        model_detail (:obj:`dict`): information about a model
        config (:obj:`dict`): configuration

    Returns:
        :obj:`tuple`:

            * :obj:`dict`: NCBI taxonomy identifier and name
            * :obj:`dict`: Genome identifier and name
            * :obj:`Reference`: structured information about the reference
            * :obj:`list` of :obj:`PubMedCentralOpenAccesGraphic`: figures of the reference
    """
    metadata_filename = os.path.join(config['final_metadata_dirname'], model_detail['model_bigg_id'] + '.yml')
    if os.path.isfile(metadata_filename):
        with open(metadata_filename, 'r') as file:
            metadata = yaml.load(file, Loader=yaml.Loader)
        taxon = metadata.get('taxon', None)
        encodes = metadata.get('encodes', None)
        reference = metadata.get('reference', None)
        thumbnails = metadata.get('thumbnails', None)

        if reference:
            reference = JournalArticle(**reference)
        if thumbnails:
            for thumbnail in thumbnails:
                thumbnail['filename'] = os.path.join(config['source_thumbnails_dirname'], thumbnail['filename'])

            thumbnails = [PubMedCentralOpenAccesGraphic(**thumbnail) for thumbnail in thumbnails]
    else:
        taxon = None
        encodes = None
        reference = None
        thumbnails = None

    if (
        taxon is not None
        and encodes is not None
        and reference is not None
        and thumbnails is not None
    ):
        return taxon, encodes, reference, thumbnails

    # NCBI id for organism
    if taxon is None or encodes is None:
        time.sleep(config['entrez_delay'])
        handle = Entrez.esearch(db="nucleotide", term='{}[Assembly] OR {}[Primary Accession]'.format(
            model_detail['genome_name'], model_detail['genome_name']), retmax=1, retmode="xml")
        record = Entrez.read(handle)
        handle.close()
        if len(record["IdList"]) > 0:
            nucleotide_id = record["IdList"][0]

            time.sleep(config['entrez_delay'])
            handle = Entrez.esummary(db="nucleotide", id=nucleotide_id, retmode="xml")
            records = list(Entrez.parse(handle))
            handle.close()
            assert len(records) == 1

            encodes = {
                'uri': 'https://www.ncbi.nlm.nih.gov/nuccore/' + str(records[0]['Id']),
                'label': str(records[0]['Title']),
            }

            taxon_id = int(records[0]['TaxId'].real)

        else:
            time.sleep(config['entrez_delay'])
            handle = Entrez.esearch(db="assembly", term='{}'.format(
                model_detail['genome_name']), retmax=1, retmode="xml")
            record = Entrez.read(handle)
            handle.close()
            if len(record["IdList"]) == 0:
                raise ValueError('Genome assembly `{}` could not be found for model `{}`'.format(
                    model_detail['genome_name'], model_detail['model_bigg_id']))

            assembly_id = str(record["IdList"][0])

            time.sleep(config['entrez_delay'])
            handle = Entrez.esummary(db="assembly", id=assembly_id, retmode="xml")
            record = Entrez.read(handle)['DocumentSummarySet']['DocumentSummary'][0]
            handle.close()

            encodes = {
                'uri': 'https://www.ncbi.nlm.nih.gov/assembly/' + assembly_id,
                'label': '{} genome assembly {}'.format(record['Organism'], record['AssemblyName']),
            }

            taxon_id = int(record['SpeciesTaxid'])

        time.sleep(config['entrez_delay'])
        handle = Entrez.esummary(db="taxonomy", id=taxon_id, retmode="xml")
        record = Entrez.read(handle)
        assert len(record) == 1
        handle.close()

        taxon = {
            'id': taxon_id,
            'name': str(record[0]['ScientificName']),
        }

    # Citation information for the associated publication
    if reference is None:
        reference = get_reference(
            model_detail['reference_id'] or None if model_detail['reference_type'] == 'pmid' else None,
            model_detail['reference_id'] or None if model_detail['reference_type'] == 'doi' else None,
            cross_ref_session=config['cross_ref_session'],
        )

    # Figures for the associated publication from open-access subset of PubMed Central
    if thumbnails is None:
        if reference and reference.pubmed_central_id:
            thumbnails = get_pubmed_central_open_access_graphics(
                reference.pubmed_central_id,
                os.path.join(config['source_thumbnails_dirname'], reference.pubmed_central_id),
                session=config['pubmed_central_open_access_session'],
            )
        else:
            thumbnails = []

    # save metadata
    metadata = {
        'taxon': taxon,
        'encodes': encodes,
        'reference': reference.__dict__,
        'thumbnails': [dataclasses.asdict(thumbnail) for thumbnail in thumbnails],
    }
    for thumbnail in metadata['thumbnails']:
        thumbnail['filename'] = os.path.relpath(thumbnail['filename'], config['source_thumbnails_dirname'])

    with open(metadata_filename, 'w') as file:
        file.write(yaml.dump(metadata))

    return (taxon, encodes, reference, thumbnails)


def export_project_metadata_for_model_to_omex_metadata(model_detail, taxon, encodes, reference, thumbnails, metadata_filename, config):
    """ Export metadata about a model to an OMEX metadata RDF-XML file

    Args:
        model_detail (:obj:`str`): information about the model
        taxon (:obj:`dict`): NCBI taxonomy identifier and name
        encodes (:obj:`dict`): Genome identifier and name
        reference (:obj:`Reference`): structured information about the reference
        thumbnails (:obj:`list` of :obj:`PubMedCentralOpenAccesGraphic`): figures of the reference
        metadata_filename (:obj:`str`): path to save metadata
        config (:obj:`dict`): configuration
    """
    created = reference.date
    last_updated = dateutil.parser.parse(model_detail['last_updated'])
    metadata = [{
        "uri": '.',
        "combine_archive_uri": BIOSIMULATIONS_ROOT_URI_FORMAT.format(model_detail['model_bigg_id']),
        'title': '{}: {} metabolism'.format(model_detail['model_bigg_id'], taxon['name']),
        'abstract': 'Flux balance analysis model of the metabolism of {}.'.format(taxon['name']),
        'keywords': [
            'metabolism',
        ],
        'description': None,
        'taxa': [
            {
                'uri': 'http://identifiers.org/taxonomy:{}'.format(taxon['id']),
                'label': taxon['name'],
            },
        ],
        'encodes': [
            {
                'uri': 'http://identifiers.org/GO:0008152',
                'label': 'metabolic process',
            },
            encodes,
        ],
        'thumbnails': [thumbnail.location for thumbnail in thumbnails],
        'sources': [],
        'predecessors': [],
        'successors': [],
        'see_also': [],
        'creators': [
            {
                'uri': None,
                'label': author,
            } for author in reference.authors
        ],
        'contributors': config['curators'],
        'identifiers': [
            {
                'uri': 'http://identifiers.org/bigg.model:{}'.format(model_detail['model_bigg_id']),
                'label': 'bigg.model:{}'.format(model_detail['model_bigg_id']),
            },
        ],
        'citations': [
            {
                'uri': (
                    'http://identifiers.org/doi:' + reference.doi
                    if reference.doi else
                    'http://identifiers.org/pubmed:' + reference.pubmed_id
                ),
                'label': reference.get_citation(),
            },
        ],
        'license': {
            'uri': 'http://bigg.ucsd.edu/license',
            'label': 'BiGG',
        },
        'funders': [],
        'created': created,
        'modified': [
            '{}-{:02d}-{:02d}'.format(last_updated.year, last_updated.month, last_updated.day),
        ],
        'other': [],
    }]
    config = Config(OMEX_METADATA_OUTPUT_FORMAT=OmexMetadataOutputFormat.rdfxml)
    BiosimulationsOmexMetaWriter().run(metadata, metadata_filename, config=config)
    _, errors, warnings = BiosimulationsOmexMetaReader().run(metadata_filename)
    assert not errors


def build_combine_archive_for_model(model_filename, archive_dirname, archive_filename, extra_contents):
    params, sims, vars, outputs = get_parameters_variables_outputs_for_simulation(
        model_filename, ModelLanguage.SBML, SteadyStateSimulation, native_ids=True)

    obj_vars = list(filter(lambda var: var.target.startswith('/sbml:sbml/sbml:model/fbc:listOfObjectives/'), vars))
    rxn_flux_vars = list(filter(lambda var: var.target.startswith('/sbml:sbml/sbml:model/sbml:listOfReactions/'), vars))

    sedml_doc = SedDocument()
    model = Model(
        id='model',
        source=os.path.basename(model_filename),
        language=ModelLanguage.SBML.value,
        changes=params,
    )
    sedml_doc.models.append(model)
    sim = sims[0]
    sedml_doc.simulations.append(sim)

    task = Task(
        id='task',
        model=model,
        simulation=sim,
    )
    sedml_doc.tasks.append(task)

    report = Report(
        id='objective',
        name='Objective',
    )
    sedml_doc.outputs.append(report)
    for var in obj_vars:
        var_id = var.id
        var_name = var.name

        var.id = 'variable_' + var_id
        var.name = None

        var.task = task
        data_gen = DataGenerator(
            id='data_generator_{}'.format(var_id),
            variables=[var],
            math=var.id,
        )
        sedml_doc.data_generators.append(data_gen)
        report.data_sets.append(DataSet(
            id=var_id,
            label=var_id,
            name=var_name,
            data_generator=data_gen,
        ))

    report = Report(
        id='reaction_fluxes',
        name='Reaction fluxes',
    )
    sedml_doc.outputs.append(report)
    for var in rxn_flux_vars:
        var_id = var.id
        var_name = var.name

        var.id = 'variable_' + var_id
        var.name = None

        var.task = task
        data_gen = DataGenerator(
            id='data_generator_{}'.format(var_id),
            variables=[var],
            math=var.id,
        )
        sedml_doc.data_generators.append(data_gen)
        report.data_sets.append(DataSet(
            id=var_id,
            label=var_id[2:] if var_id.startswith('R_') else var_id,
            name=var_name if len(rxn_flux_vars) < 4000 else None,
            data_generator=data_gen,
        ))

    # make directory for archive
    if os.path.isdir(archive_dirname):
        shutil.rmtree(archive_dirname)
    os.makedirs(archive_dirname)
    shutil.copyfile(model_filename, os.path.join(archive_dirname, os.path.basename(model_filename)))

    SedmlSimulationWriter().run(sedml_doc, os.path.join(archive_dirname, 'simulation.sedml'))

    # form a description of the archive
    archive = CombineArchive()
    archive.contents.append(CombineArchiveContent(
        location=os.path.basename(model_filename),
        format=CombineArchiveContentFormat.SBML.value,
    ))
    archive.contents.append(CombineArchiveContent(
        location='simulation.sedml',
        format=CombineArchiveContentFormat.SED_ML.value,
        master=True,
    ))
    for local_path, extra_content in extra_contents.items():
        shutil.copyfile(local_path, os.path.join(archive_dirname, extra_content.location))
        archive.contents.append(extra_content)

    # save archive to file
    CombineArchiveWriter().run(archive, archive_dirname, archive_filename)


def import_projects(config):
    """ Download the source database, convert into COMBINE/OMEX archives, simulate the archives, and submit them to BioSimulations

    Args:
        config (:obj:`dict`): configuration
    """

    # create directories for source files, thumbnails, projects, and simulation results
    if not os.path.isdir(config['source_models_dirname']):
        os.makedirs(config['source_models_dirname'])
    if not os.path.isdir(config['source_visualizations_dirname']):
        os.makedirs(config['source_visualizations_dirname'])
    if not os.path.isdir(config['source_thumbnails_dirname']):
        os.makedirs(config['source_thumbnails_dirname'])

    if not os.path.isdir(config['final_visualizations_dirname']):
        os.makedirs(config['final_visualizations_dirname'])
    if not os.path.isdir(config['final_metadata_dirname']):
        os.makedirs(config['final_metadata_dirname'])
    if not os.path.isdir(config['final_projects_dirname']):
        os.makedirs(config['final_projects_dirname'])
    if not os.path.isdir(config['final_simulation_results_dirname']):
        os.makedirs(config['final_simulation_results_dirname'])

    # read import status file
    if os.path.isfile(config['status_filename']):
        with open(config['status_filename'], 'r') as file:
            status = yaml.load(file, Loader=yaml.Loader)
    else:
        status = {}

    # read import issues file
    with open(config['issues_filename'], 'r') as file:
        issues = yaml.load(file, Loader=yaml.Loader)

    # read thumbnails file
    if os.path.isfile(config['thumbnails_filename']):
        with open(config['thumbnails_filename'], 'r') as file:
            thumbnails_curation = yaml.load(file, Loader=yaml.Loader)
        for model in thumbnails_curation.values():
            for thumbnail in model:
                thumbnail['filename'] = os.path.join(config['source_thumbnails_dirname'], thumbnail['filename'])
    else:
        thumbnails_curation = {}

    # read extra visualizations file
    if os.path.isfile(config['extra_visualizations_filename']):
        with open(config['extra_visualizations_filename'], 'r') as file:
            extra_visualizations_curation = yaml.load(file, Loader=yaml.Loader)
    else:
        extra_visualizations_curation = {}

    # get a list of all models available in the source database
    models = get_models(config)

    # filter to selected projects
    if config['project_ids'] is not None:
        models = list(filter(lambda model: model['bigg_id'] in config['project_ids'], models))

    # limit the models to import by number of reactions (used for testing)
    if config['max_num_reactions'] is not None:
        models = list(filter(lambda model: model['reaction_count'] < config['max_num_reactions'], models))

    # limit the number of models to import
    models = models[config['first_project']:]
    models = models[0:config['max_projects']]

    # get the details of each model
    model_details = []
    update_times = {}
    for i_model, model in enumerate(models):
        print('Retrieving {} of {}: {} ...'.format(i_model + 1, len(models), model['bigg_id']))

        # update status
        update_times[model['bigg_id']] = datetime.datetime.utcnow()

        # get the details of the model and download it from the source database
        last_updated = status.get(model['bigg_id'], {}).get('updated', None)
        if last_updated:
            last_updated = dateutil.parser.parse(last_updated)

        model_detail = get_model_details(model, last_updated, config)
        model_details.append(model_detail)
    models = model_details

    # filter out models that don't need to be imported because they've already been imported and haven't been updated
    if not config['update_simulation_runs']:
        models = list(filter(
            lambda model:
            (
                model['model_bigg_id'] not in status
                or not status[model['model_bigg_id']]['runbiosimulationsId']
                or (
                    (dateutil.parser.parse(model['last_updated']) + datetime.timedelta(1))
                    > dateutil.parser.parse(status[model['model_bigg_id']]['updated'])
                )
            ),
            models
        ))

    # filter out models with issues
    models = list(filter(lambda model: model['model_bigg_id'] not in issues, models))

    # get S3 bucket to save archives
    s3 = boto3.resource('s3',
                        endpoint_url=config['bucket_endpoint'],
                        aws_access_key_id=config['bucket_access_key_id'],
                        aws_secret_access_key=config['bucket_secret_access_key'])
    bucket = s3.Bucket(config['bucket_name'])

    # get authorization for BioSimulations API
    auth = biosimulators_utils.biosimulations.utils.get_authorization_for_client(
        config['biosimulations_api_client_id'], config['biosimulations_api_client_secret'])

    # download models, convert them to COMBINE/OMEX archives, simulate them, and deposit them to the BioSimulations database
    for i_model, model in enumerate(models):
        project_filename = os.path.join(config['final_projects_dirname'], model['model_bigg_id'] + '.omex')
        if not os.path.isfile(project_filename) or config['update_combine_archives']:
            model_filename = os.path.join(config['source_models_dirname'], model['model_bigg_id'] + '.xml')

            # get additional metadata about the model
            print('Getting metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
            taxon, encodes, reference, thumbnails = get_metadata_for_model(model, config)

            # filter out disabled thumbnails
            if thumbnails_curation.get(model['model_bigg_id'], []):
                thumbnails = []
                for thumbnail in thumbnails_curation[model['model_bigg_id']]:
                    if thumbnail['enabled']:
                        thumbnails.append(PubMedCentralOpenAccesGraphic(
                            id=thumbnail['id'],
                            label=thumbnail['label'],
                            filename=thumbnail['filename'],
                        ))
            else:
                thumbnails_curation[model['model_bigg_id']] = [
                    {
                        'id': thumbnail.id,
                        'label': thumbnail.label,
                        'filename': thumbnail.filename,
                        'enabled': True,
                    }
                    for thumbnail in thumbnails
                ]
            thumbnails = thumbnails[0:config['max_thumbnails']]
            for thumbnail in thumbnails:
                thumbnail.location = reference.pubmed_central_id + '-' + os.path.basename(thumbnail.id) + '.jpg'
                thumbnail.format = CombineArchiveContentFormat.JPEG

            # convert Escher map to Vega and add to thumbnails
            escher_maps = model['escher_maps'] + sorted((
                {'map_name': name} for name in set(extra_visualizations_curation.get(model['model_bigg_id'], [])).difference(
                    set(map['map_name'] for map in model['escher_maps'])
                )),
                key=lambda map: map['map_name'],
            )

            for escher_map in escher_maps:
                map_name = escher_map['map_name']
                standardized_map_name = re.sub(r'[^a-zA-Z0-9\.]', '-', map_name)
                escher_filename = os.path.join(config['source_visualizations_dirname'], standardized_map_name + '.json')

                vega_filename = os.path.join(config['final_visualizations_dirname'], standardized_map_name + '.vg.json')
                if not os.path.isfile(vega_filename):
                    reaction_fluxes_data_set = {
                        'sedmlUri': ['simulation.sedml', 'reaction_fluxes'],
                    }
                    escher_to_vega(reaction_fluxes_data_set, escher_filename, vega_filename)

                png_filename = os.path.join(config['source_visualizations_dirname'], map_name + '.png')
                if os.path.isfile(png_filename):
                    thumbnails.append(mock.Mock(
                        filename=png_filename,
                        location=standardized_map_name + '.png',
                        format=CombineArchiveContentFormat.PNG,
                    ))

            # export metadata to RDF
            print('Exporting project metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
            project_metadata_filename = os.path.join(config['final_metadata_dirname'], model['model_bigg_id'] + '.rdf')
            export_project_metadata_for_model_to_omex_metadata(model, taxon, encodes, reference, thumbnails,
                                                               project_metadata_filename, config)

            # print('Exporting model metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
            # model_metadata_filename = os.path.join(config['final_metadata_dirname'], model['model_bigg_id'] + '-omex-metadata.rdf')
            # build_omex_meta_file_for_model(model_filename, model_metadata_filename, metadata_format=OmexMetaOutputFormat.rdfxml_abbrev)

            # package model into COMBINE/OMEX archive
            print('Converting model {} of {}: {} ...'.format(i_model + 1, len(models), model['model_bigg_id']))

            extra_contents = {}
            extra_contents[project_metadata_filename] = CombineArchiveContent(
                location='metadata.rdf',
                format=CombineArchiveContentFormat.OMEX_METADATA,
            )
            # extra_contents[model_metadata_filename] = CombineArchiveContent(
            #     location=model['model_bigg_id'] + '.rdf',
            #     format=CombineArchiveContentFormat.OMEX_METADATA,
            # )
            extra_contents[config['source_license_filename']] = CombineArchiveContent(
                location='LICENSE',
                format=CombineArchiveContentFormat.TEXT,
            )
            for escher_map in escher_maps:
                map_name = escher_map['map_name']
                standardized_map_name = re.sub(r'[^a-zA-Z0-9\.]', '-', map_name)
                escher_filename = os.path.join(config['source_visualizations_dirname'], standardized_map_name + '.json')
                vega_filename = os.path.join(config['final_visualizations_dirname'], standardized_map_name + '.vg.json')
                extra_contents[escher_filename] = CombineArchiveContent(
                    location=standardized_map_name + '.escher.json',
                    format=CombineArchiveContentFormat.Escher,
                )
                extra_contents[vega_filename] = CombineArchiveContent(
                    location=standardized_map_name + '.vg.json',
                    format=CombineArchiveContentFormat.Vega,
                )
            for thumbnail in thumbnails:
                extra_contents[thumbnail.filename] = CombineArchiveContent(
                    location=thumbnail.location,
                    format=thumbnail.format,
                )

            project_dirname = os.path.join(config['final_projects_dirname'], model['model_bigg_id'])
            project_filename = os.path.join(config['final_projects_dirname'], model['model_bigg_id'] + '.omex')

            build_combine_archive_for_model(model_filename, project_dirname, project_filename, extra_contents=extra_contents)

        # simulate COMBINE/OMEX archives
        prev_objective = status.get(model['model_bigg_id'], {}).get('objective', None)
        prev_duration = status.get(model['model_bigg_id'], {}).get('duration', None)

        if config['simulate_projects'] and (
            config['update_combine_archives']
            or config['update_simulations']
            or prev_objective is None
        ):
            print('Simulating model {} of {}: {} ...'.format(i_model + 1, len(models), model['model_bigg_id']))
            out_dirname = os.path.join(config['final_simulation_results_dirname'], model['model_bigg_id'])
            biosimulators_utils_config = Config(COLLECT_COMBINE_ARCHIVE_RESULTS=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", BioSimulatorsWarning)
                results, log = biosimulators_cobrapy.exec_sedml_docs_in_combine_archive(
                    project_filename, out_dirname, config=biosimulators_utils_config)
            if log.exception:
                print('Simulation of `{}` failed'.format(model['model_bigg_id']))
                raise log.exception
            objective = results['simulation.sedml']['objective']['obj'].tolist()
            print('  {}: Objective: {}'.format(model['model_bigg_id'], objective))
            if objective <= 0:
                raise ValueError('`{}` is not a meaningful simulation.'.format(model['model_bigg_id']))
            duration = log.duration
        else:
            objective = prev_objective
            duration = prev_duration

        # submit COMBINE/OMEX archive to BioSimulations
        if config['dry_run']:
            runbiosimulations_id = status.get(model['model_bigg_id'], {}).get('runbiosimulationsId', None)
            updated = status.get(model['model_bigg_id'], {}).get('updated', None)
        else:
            print('Submitting model {} of {}: {} ...'.format(i_model + 1, len(models), model['model_bigg_id']))

            name = model['model_bigg_id']
            if config['publish_projects']:
                project_id = name
            else:
                project_id = None

            project_bucket_key = '{}.omex'.format(model['model_bigg_id'])
            bucket.upload_file(project_filename, project_bucket_key)
            project_url = '{}/{}/{}'.format(config['bucket_endpoint'], config['bucket_name'], project_bucket_key)

            runbiosimulations_id = biosimulators_utils.biosimulations.utils.run_simulation_project(
                name, project_url, 'cobrapy', project_id=project_id, purpose='academic', auth=auth)
            updated = str(update_times[model['model_bigg_id']])

        # output status
        status[model['model_bigg_id']] = {
            'created': status.get(model['model_bigg_id'], {}).get('created', str(update_times[model['model_bigg_id']])),
            'updated': updated,
            'objective': objective,
            'duration': duration,
            'runbiosimulationsId': runbiosimulations_id,
            'biosimulationsId': model['model_bigg_id'],
        }
        with open(config['status_filename'], 'w') as file:
            file.write(yaml.dump(status))

        thumbnails_curation_copy = copy.deepcopy(thumbnails_curation)
        for model in thumbnails_curation_copy.values():
            for thumbnail in model:
                thumbnail['filename'] = os.path.relpath(thumbnail['filename'], config['source_thumbnails_dirname'])
        with open(config['thumbnails_filename'], 'w') as file:
            file.write(yaml.dump(thumbnails_curation_copy))
