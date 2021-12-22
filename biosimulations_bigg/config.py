import datetime
import os
import pkg_resources
import requests_cache
import yaml


__all__ = ['get_config']

BASE_DIR = pkg_resources.resource_filename('biosimulations_bigg', '.')


def get_config(
        source_api_endpoint='http://bigg.ucsd.edu/api/v2',
        source_model_file_endpoint='http://bigg.ucsd.edu/static',
        source_map_file_endpoint='http://bigg.ucsd.edu/escher_map_json',
        source_dirname=None,
        source_license_filename=None,
        sessions_dirname=None,
        final_dirname=None,
        curators_filename=None,
        issues_filename=None,
        status_filename=None,
        thumbnails_filename=None,
        extra_visualizations_filename=None,
        max_models=None,
        max_num_reactions=None,
        max_thumbnails=None,
        update_combine_archives=False,
        update_simulation_runs=False,
        simulate_models=True,
        publish_models=True,
        entrez_delay=5.,
        biosimulations_api_client_id=None,
        biosimulations_api_client_secret=None,
        dry_run=False,
):
    """ Get a configuration

    Args:
        source_api_endpoint (obj:`str`, optional): endpoint for retrieving metadata about BiGG models
        source_model_file_endpoint (obj:`str`, optional): endpoint for retrieving files for BiGG models
        source_map_file_endpoint (obj:`str`, optional): endpoint for retrieving files for Escher visualizations
        source_dirname (obj:`str`, optional): directory where source models, metabolic flux maps, and thumbnails should be stored
        source_license_filename (obj:`str`, optional): path to BiGG license to copy into COMBINE/OMEX archives
        sessions_dirname (obj:`str`, optional): directory where cached HTTP sessions should be stored
        final_dirname (obj:`str`, optional): directory where created SED-ML, metadata, and COMBINE/OMEX archives should be stored
        curators_filename (obj:`str`, optional): path which describes the people who helped curator the repository
        issues_filename (obj:`str`, optional): path to issues which prevent some models from being imported
        status_filename (obj:`str`, optional): path to save the import status of each model
        thumbnails_filename (obj:`str`, optional): path to curated list of good thumbnails
        extra_visualizations_filename (obj:`str`, optional): path to curated list of additional Escher diagrams to use with models
        max_models (:obj:`int`, optional): maximum number of models to download, convert, execute, and submit; used for testing
        max_num_reactions (:obj:`int`, optional): maximum size model to import; used for testing
        max_thumbnails (:obj:`int`, optional): maximum number of thumbnails to use; used for testing
        update_combine_archives (:obj:`bool`, optional): whether to update COMBINE archives even if they already exist; used for testing
        update_simulation_runs (:obj:`bool`, optional): whether to update models even if they have already been imported; used for testing
        simulate_models (:obj:`bool`, optional): whether to simulate models; used for testing
        publish_models (:obj:`bool`, optional): whether to pushlish models; used for testing
        entrez_delay (:obj:`float`, optional): delay in between Entrez queries
        biosimulations_api_client_id (:obj:`str`, optional): id for client to the BioSimulations API
        biosimulations_api_client_secret (:obj:`str`, optional): secret for client to the BioSimulations API
        dry_run (:obj:`bool`, optional): whether to submit models to BioSimulations or not; used for testing

    Returns:
        obj:`dict`: configuration
    """

    if source_dirname is None:
        source_dirname = os.getenv('SOURCE_DIRNAME', os.path.join(BASE_DIR, 'source'))
    if source_license_filename is None:
        source_license_filename = os.getenv('SOURCE_LICENSE_FILENAME', os.path.join(BASE_DIR, 'source', 'LICENSE'))
    if sessions_dirname is None:
        sessions_dirname = os.getenv('SESSIONS_DIRNAME', os.path.join(BASE_DIR, 'source'))
    if final_dirname is None:
        final_dirname = os.getenv('FINAL_DIRNAME', os.path.join(BASE_DIR, 'final'))
    if curators_filename is None:
        curators_filename = os.getenv('CURATORS_FILENAME', os.path.join(BASE_DIR, 'final', 'curators.yml'))
    if issues_filename is None:
        issues_filename = os.getenv('ISSUES_FILENAME', os.path.join(BASE_DIR, 'final', 'issues.yml'))
    if status_filename is None:
        status_filename = os.getenv('STATUS_FILENAME', os.path.join(BASE_DIR, 'final', 'status.yml'))
    if thumbnails_filename is None:
        thumbnails_filename = os.getenv('THUMBNAILS_FILENAME', os.path.join(BASE_DIR, 'final', 'thumbnails.yml'))
    if extra_visualizations_filename is None:
        extra_visualizations_filename = os.getenv('EXTRA_VISUALIZATIONS_FILENAME',
                                                  os.path.join(BASE_DIR, 'final', 'extra-visualizations.yml'))
    if biosimulations_api_client_id is None:
        biosimulations_api_client_id = os.getenv('BIOSIMULATIONS_API_CLIENT_ID')
    if biosimulations_api_client_secret is None:
        biosimulations_api_client_secret = os.getenv('BIOSIMULATIONS_API_CLIENT_SECRET')

    with open(curators_filename, 'r') as file:
        curators = yaml.load(file, Loader=yaml.Loader)

    return {
        'source_api_endpoint': source_api_endpoint,
        'source_model_file_endpoint': source_model_file_endpoint,
        'source_map_file_endpoint': source_map_file_endpoint,

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
        'thumbnails_filename': thumbnails_filename,
        'extra_visualizations_filename': extra_visualizations_filename,

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
        'max_thumbnails': max_thumbnails,
        'update_combine_archives': update_combine_archives,
        'update_simulation_runs': update_simulation_runs,
        'simulate_models': simulate_models,
        'publish_models': publish_models,
        'entrez_delay': entrez_delay,
        'biosimulations_api_client_id': biosimulations_api_client_id,
        'biosimulations_api_client_secret': biosimulations_api_client_secret,
        'dry_run': dry_run,
    }
