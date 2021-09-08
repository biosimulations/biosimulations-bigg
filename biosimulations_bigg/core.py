from Bio import Entrez
from biosimulators_utils.combine.data_model import CombineArchive, CombineArchiveContent, CombineArchiveContentFormat
from biosimulators_utils.combine.io import CombineArchiveWriter
from biosimulators_utils.config import Config
# from biosimulators_utils.omex_meta.data_model import OmexMetaOutputFormat
from biosimulators_utils.omex_meta.io import BiosimulationsOmexMetaWriter, BiosimulationsOmexMetaReader
# from biosimulators_utils.omex_meta.utils import build_omex_meta_file_for_model
from biosimulators_utils.ref.data_model import Reference, PubMedCentralOpenAccesGraphic  # noqa: F401
from biosimulators_utils.ref.utils import get_reference, get_pubmed_central_open_access_graphics
from biosimulators_utils.sedml.data_model import (
    SedDocument, Model, ModelLanguage, SteadyStateSimulation,
    Task, DataGenerator, Report, DataSet)
from biosimulators_utils.sedml.io import SedmlSimulationWriter
from biosimulators_utils.sedml.model_utils import get_parameters_variables_for_simulation
from biosimulators_utils.viz.vega.escher import escher_to_vega
from biosimulators_utils.warnings import BioSimulatorsWarning
import biosimulators_cobrapy
import biosimulators_utils.biosimulations.utils
import datetime
import dateutil.parser
import os
import pkg_resources
import requests_cache
import shutil
import tempfile
import time
import warnings
import yaml

BASE_DIR = pkg_resources.resource_filename('biosimulations_bigg', '.')

Entrez.email = os.getenv('ENTREZ_EMAIL', None)

SOURCE_API_ENDPOINT = 'http://bigg.ucsd.edu/api/v2'
SOURCE_MODEL_FILES_ENDPOINT = 'http://bigg.ucsd.edu/static'
SOURCE_MAP_FILE_ENDPOINT = 'http://bigg.ucsd.edu/escher_map_json'

__all__ = ['import_models', 'get_config']


def get_config(
        source_dirname=os.path.join(BASE_DIR, 'source'),
        source_license_filename=os.path.join(BASE_DIR, 'source', 'LICENSE'),
        sessions_dirname=os.path.join(BASE_DIR, 'source'),
        final_dirname=os.path.join(BASE_DIR, 'final'),
        curators_filename=os.path.join(BASE_DIR, 'final', 'curators.yml'),
        issues_filename=os.path.join(BASE_DIR, 'final', 'issues.yml'),
        status_filename=os.path.join(BASE_DIR, 'final', 'status.yml'),
        max_models=None,
        max_num_reactions=None,
        dry_run=False,
):
    """ Get a configuration

    Args:
        source_dirname (obj:`str`, optional): directory where source models, metabolic flux maps, and thumbnails should be stored
        source_license_filename (obj:`str`, optional): path to BiGG license to copy into COMBINE/OMEX archives
        sessions_dirname (obj:`str`, optional): directory where cached HTTP sessions should be stored
        final_dirname (obj:`str`, optional): directory where created SED-ML, metadata, and COMBINE/OMEX archives should be stored
        curators_filename (obj:`str`, optional): path which describes the people who helped curator the repository
        issues_filename (obj:`str`, optional): path to issues which prevent some models from being imported
        status_filename (obj:`str`, optional): path to save the import status of each model
        max_models (:obj:`int`, optional): maximum number of models to download, convert, execute, and submit; used for testing
        max_num_reactions (:obj:`int`, optional): maximum size model to import; used for testing
        dry_run (:obj:`bool`, optional): whether to submit models to BioSimulations or not; used for testing

    Returns:
        obj:`dict`: configuration
    """

    with open(curators_filename, 'r') as file:
        curators = yaml.load(file, Loader=yaml.Loader)

    return {
        'source_models_dirname': os.path.join(source_dirname, 'models'),
        'source_visualizations_dirname': os.path.join(source_dirname, 'visualizations'),
        'source_thumbnails_dirname': os.path.join(source_dirname, 'thumbnails'),
        'source_license_filename': source_license_filename,

        'final_visualizations_dirname': os.path.join(final_dirname, 'visualizations'),
        'final_metadata_dirname': os.path.join(final_dirname, 'metadata'),
        'final_projects_dirname': os.path.join(final_dirname, 'projects'),
        'final_simulation_results_dirname': os.path.join(final_dirname, 'simulation-results'),

        'curators': curators,
        'issues_filename': issues_filename,
        'status_filename': status_filename,

        'source_session': requests_cache.CachedSession(
            os.path.join(sessions_dirname, 'source'),
            expire_after=datetime.timedelta(4 * 7)),
        'cross_ref_session': requests_cache.CachedSession(
            os.path.join(sessions_dirname, 'crossref'),
            expire_after=datetime.timedelta(4 * 7)),
        'pubmed_central_open_access_session': requests_cache.CachedSession(
            os.path.join(sessions_dirname, 'pubmed-central-open-access'),
            expire_after=datetime.timedelta(4 * 7)),

        'max_models': max_models,
        'max_num_reactions': max_num_reactions,
        'dry_run': dry_run,
    }


def get_models(config):
    """ Get a list of the models in the source database

    Args:
        config (:obj:`dict`): configuration

    Returns:
        :obj:`list` of :obj:`dict`: models
    """
    response = config['source_session'].get(SOURCE_API_ENDPOINT + '/models')
    response.raise_for_status()
    models = response.json()['results']
    models.sort(key=lambda model: model['bigg_id'])
    return models


def get_model_details(model, config):
    """ Get the details of a model from the source database and download the associated files

    Args:
        model (:obj:`dict`): model
        config (:obj:`dict`): configuration

    Returns:
        :obj:`dict`: detailed information about the model
    """
    # get information about the model
    response = config['source_session'].get(SOURCE_API_ENDPOINT + '/models/' + model['bigg_id'])
    response.raise_for_status()
    model_detail = response.json()

    # download the file for the model
    model_filename = os.path.join(config['source_models_dirname'], model['bigg_id'] + '.xml')
    if not os.path.isfile(model_filename):
        response = config['source_session'].get(SOURCE_MODEL_FILES_ENDPOINT + '/models/{}.xml'.format(model['bigg_id']))
        response.raise_for_status()
        with open(model_filename, 'wb') as file:
            file.write(response.content)

    # download flux map visualizations associated with the model
    for escher_map in model_detail['escher_maps']:
        escher_filename = os.path.join(config['source_visualizations_dirname'], escher_map['map_name'] + '.json')
        if not os.path.isfile(escher_filename):
            response = config['source_session'].get(SOURCE_MAP_FILE_ENDPOINT + '/' + escher_map['map_name'])
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
            * :obj:`Reference`: structured information about the reference
            * :obj:`list` of :obj:`PubMedCentralOpenAccesGraphic`: figures of the reference
    """
    # delay to prevent overloading NCBI servers
    time.sleep(0.5)

    # NCBI id for organism
    handle = Entrez.esearch(db="nucleotide", term='{}[Assembly] OR {}[Primary Accession]'.format(
        model_detail['genome_name'], model_detail['genome_name']), retmax=1, retmode="xml")
    record = Entrez.read(handle)
    handle.close()
    if len(record["IdList"]) > 0:
        nucleotide_id = record["IdList"][0]

        handle = Entrez.esummary(db="nucleotide", id=nucleotide_id, retmode="xml")
        records = list(Entrez.parse(handle))
        handle.close()
        assert len(records) == 1

        taxon_id = records[0]['TaxId'].real

    else:
        handle = Entrez.esearch(db="assembly", term='{}'.format(
            model_detail['genome_name']), retmax=1, retmode="xml")
        record = Entrez.read(handle)
        handle.close()
        if len(record["IdList"]) == 0:
            raise ValueError('Genome assembly `{}` could not be found for model `{}`'.format(
                model_detail['genome_name'], model_detail['model_bigg_id']))

        assembly_id = record["IdList"][0]

        handle = Entrez.esummary(db="assembly", id=assembly_id, retmode="xml")
        record = Entrez.read(handle)['DocumentSummarySet']['DocumentSummary'][0]
        handle.close()

        taxon_id = int(record['SpeciesTaxid'])

    handle = Entrez.esummary(db="taxonomy", id=taxon_id, retmode="xml")
    record = Entrez.read(handle)
    assert len(record) == 1
    handle.close()

    taxon = {
        'id': taxon_id,
        'name': record[0]['ScientificName'],
    }

    # Citation information for the associated publication
    reference = get_reference(
        model_detail['reference_id'] or None if model_detail['reference_type'] == 'pmid' else None,
        model_detail['reference_id'] or None if model_detail['reference_type'] == 'doi' else None,
        cross_ref_session=config['cross_ref_session'],
    )

    # Figures for the associated publication from open-access subset of PubMed Central
    if reference and reference.pubmed_central_id:
        thumbnails = get_pubmed_central_open_access_graphics(
            reference.pubmed_central_id,
            os.path.join(config['source_thumbnails_dirname'], reference.pubmed_central_id),
            session=config['pubmed_central_open_access_session'],
        )
    else:
        thumbnails = []

    return (taxon, reference, thumbnails)


def export_project_metadata_for_model_to_omex_metadata(model_detail, taxon, reference, thumbnails, metadata_filename, config):
    """ Export metadata about a model to an OMEX metadata RDF-XML file

    Args:
        model_detail (:obj:`str`): information about the model
        taxon (:obj:`dict`): NCBI taxonomy identifier and name
        reference (:obj:`Reference`): structured information about the reference
        thumbnails (:obj:`list` of :obj:`PubMedCentralOpenAccesGraphic`): figures of the reference
        metadata_filename (:obj:`str`): path to save metadata
        config (:obj:`dict`): configuration
    """
    created = reference.date
    last_updated = dateutil.parser.parse(model_detail['last_updated'])
    metadata = [{
        "uri": '.',
        'title': model_detail['model_bigg_id'],
        'abstract': 'Flux balance analysis model of the metabolism of {}.'.format(taxon['name']),
        'keywords': [
            'metabolism',
            'BiGG',
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
        ],
        'thumbnails': [reference.pubmed_central_id + '-' + os.path.basename(thumbnail.id) + '.jpg' for thumbnail in thumbnails],
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
    BiosimulationsOmexMetaWriter().run(metadata, metadata_filename)
    _, errors, warnings = BiosimulationsOmexMetaReader().run(metadata_filename)
    assert not errors


def build_combine_archive_for_model(model_filename, archive_filename, extra_contents):
    params, sims, vars = get_parameters_variables_for_simulation(model_filename, ModelLanguage.SBML, SteadyStateSimulation, native_ids=True)

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
            label=var_id,
            name=var_name if len(rxn_flux_vars) < 4000 else None,
            data_generator=data_gen,
        ))

    # make temporary directory for archive
    archive_dirname = tempfile.mkdtemp()
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
    ))
    for local_path, extra_content in extra_contents.items():
        shutil.copyfile(local_path, os.path.join(archive_dirname, extra_content.location))
        archive.contents.append(extra_content)

    # save archive to file
    CombineArchiveWriter().run(archive, archive_dirname, archive_filename)

    # clean up temporary directory for archive
    shutil.rmtree(archive_dirname)


def import_models(config):
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

    # get a list of all models available in the source database
    models = get_models(config)

    # limit the models to import by number of reactions (used for testing)
    if config['max_num_reactions'] is not None:
        models = list(filter(lambda model: model['reaction_count'] < config['max_num_reactions'], models))

    # limit the number of models to import
    models = models[0:config['max_models']]

    # get the details of each model
    model_details = []
    update_times = {}
    for i_model, model in enumerate(models):
        print('Retrieving {} of {}: {} ...'.format(i_model + 1, len(models), model['bigg_id']))

        # update status
        update_times[model['bigg_id']] = datetime.datetime.utcnow()

        # get the details of the model and download it from the source database
        model_detail = get_model_details(model, config)
        model_details.append(model_detail)
    models = model_details

    # filter out models that don't need to be imported because they've already been imported and haven't been updated
    models = list(filter(
        lambda model:
        (
            model['model_bigg_id'] not in status
            or (
                (dateutil.parser.parse(model['last_updated']) + datetime.timedelta(1))
                > dateutil.parser.parse(status[model['model_bigg_id']]['updated'])
            )
        ),
        models
    ))

    # filter out models with issues
    models = list(filter(lambda model: model['model_bigg_id'] not in issues, models))

    # download models, convert them to COMBINE/OMEX archives, simulate them, and deposit them to the BioSimulations database
    for i_model, model in enumerate(models):
        model_filename = os.path.join(config['source_models_dirname'], model['model_bigg_id'] + '.xml')

        # convert Escher map to Vega
        for escher_map in model['escher_maps']:
            escher_filename = os.path.join(config['source_visualizations_dirname'], escher_map['map_name'] + '.json')
            vega_filename = os.path.join(config['final_visualizations_dirname'], escher_map['map_name'] + '.json')
            if not os.path.isfile(vega_filename):
                reaction_fluxes_data_set = {
                    'sedmlUri': ['simulation.sedml', 'reaction_fluxes'],
                }
                escher_to_vega(reaction_fluxes_data_set, escher_filename, vega_filename)

        # get additional metadata about the model
        print('Getting metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
        taxon, reference, thumbnails = get_metadata_for_model(model, config)

        # export metadata to RDF
        print('Exporting project metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
        project_metadata_filename = os.path.join(config['final_metadata_dirname'], model['model_bigg_id'] + '.rdf')
        export_project_metadata_for_model_to_omex_metadata(model, taxon, reference, thumbnails, project_metadata_filename, config)

        # print('Exporting model metadata for {} of {}: {}'.format(i_model + 1, len(models), model['model_bigg_id']))
        # model_metadata_filename = os.path.join(config['final_metadata_dirname'], model['model_bigg_id'] + '-omex-metadata.rdf')
        # build_omex_meta_file_for_model(model_filename, model_metadata_filename, metadata_format=OmexMetaOutputFormat.rdfxml_abbrev)

        # package model into COMBINE/OMEX archive
        print('Converting model {} of {}: {} ...'.format(i_model + 1, len(models), model['model_bigg_id']))

        project_filename = os.path.join(config['final_projects_dirname'], model['model_bigg_id'] + '.omex')

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
        for escher_map in model['escher_maps']:
            escher_filename = os.path.join(config['source_visualizations_dirname'], escher_map['map_name'] + '.json')
            vega_filename = os.path.join(config['final_visualizations_dirname'], escher_map['map_name'] + '.json')
            extra_contents[escher_filename] = CombineArchiveContent(
                location=escher_map['map_name'] + '.escher.json',
                format=CombineArchiveContentFormat.Escher,
            )
            extra_contents[vega_filename] = CombineArchiveContent(
                location=escher_map['map_name'] + '.vega.json',
                format=CombineArchiveContentFormat.Vega,
            )
        for thumbnail in thumbnails:
            extra_contents[thumbnail.filename] = CombineArchiveContent(
                location=reference.pubmed_central_id + '-' + os.path.basename(thumbnail.id) + '.jpg',
                format=CombineArchiveContentFormat.JPEG,
            )

        build_combine_archive_for_model(model_filename, project_filename, extra_contents=extra_contents)

        # simulate COMBINE/OMEX archives
        print('Simulating model {} of {}: {} ...'.format(i_model + 1, len(models), model['model_bigg_id']))

        project_filename = os.path.join(config['final_projects_dirname'], model['model_bigg_id'] + '.omex')
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

        # submit COMBINE/OMEX archive to BioSimulations
        if not config['dry_run']:
            name = model['model_bigg_id']
            runbiosimulations_id = biosimulators_utils.biosimulations.utils.submit_project_to_runbiosimulations(name, project_filename, 'cobrapy')
        else:
            runbiosimulations_id = None

        # output status
        status[model['model_bigg_id']] = {
            'created': status.get(model['model_bigg_id'], {}).get('created', str(update_times[model['model_bigg_id']])),
            'updated': str(update_times[model['model_bigg_id']]),
            'objective': objective,
            'duration': duration,
            'runbiosimulationsId': runbiosimulations_id,
        }
        with open(config['status_filename'], 'w') as file:
            file.write(yaml.dump(status))