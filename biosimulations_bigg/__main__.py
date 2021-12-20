from .core import import_models, get_config
from ._version import __version__
from biosimulators_utils.config import get_config as get_biosimulators_config
import biosimulators_utils.biosimulations.utils
import cement
import requests
import sys
import yaml


class BaseController(cement.Controller):
    """ Base controller for command line application """

    class Meta:
        label = 'base'
        description = "Utilities for publishing BiGG to BioSimulations"
        help = "Utilities for publishing BiGG to BioSimulations"
        arguments = [
            (['-v', '--version'], dict(
                action='version',
                version=__version__,
            )),
        ]

    @cement.ex(hide=True)
    def _default(self):
        self._parser.print_help()


class PublishController(cement.Controller):
    """ Publish models from BiGG to BioSimulations

    * Download models
    * Download visualizations
    * Download metadata
    * Generate SED-ML files for models
    * Convert visualizations to Vega format
    * Expand taxonomy metadata using NCBI Taxonomy
    * Expand citation metadata using PubMed and CrossRef
    * Obtain thumbnail images using PubMed Central
    * Encode metadata into OMEX metadata files
    * Package project into COMBINE/OMEX archives
    * Submit simulation runs for archives to runBioSimulations
    * Publish simulation runs to BioSimulations
    """

    class Meta:
        label = 'publish'
        stacked_on = 'base'
        stacked_type = 'nested'
        help = "Publish models from BiGG to BioSimulations"
        description = "Publish models from BiGG to BioSimulations"
        arguments = [
            (
                ['--max-models'],
                dict(
                    type=int,
                    default=None,
                    help='Maximum number of models to import. Used for testing.',
                ),
            ),
            (
                ['--max-num-reactions'],
                dict(
                    type=int,
                    default=None,
                    help='Maximum size model to import. Used for testing.',
                ),
            ),
            (
                ['--update-combine-archives'],
                dict(
                    action='store_true',
                    help='If set, update models even if they have already been imported. Used for testing.'
                ),
            ),
            (
                ['--update-simulation-runs'],
                dict(
                    action='store_true',
                    help='If set, update models even if they have already been imported. Used for testing.'
                ),
            ),
            (
                ['--skip-simulation'],
                dict(
                    action='store_true',
                    help='If set, do not simulate models. Used for testing.',
                ),
            ),
            (
                ['--skip-publication'],
                dict(
                    action='store_true',
                    help='If set, do not publish models. Used for testing.',
                ),
            ),
            (
                ['--dry-run'],
                dict(
                    action='store_true',
                    help='If set, do not submit models to BioSimulations. Used for testing.'
                ),
            ),
        ]

    @ cement.ex(hide=True)
    def _default(self):
        args = self.app.pargs

        config = get_config(max_models=args.max_models, max_num_reactions=args.max_num_reactions,
                            update_combine_archives=args.update_combine_archives,
                            update_simulation_runs=args.update_simulation_runs,
                            simulate_models=not args.skip_simulation,
                            publish_models=not args.skip_publication,
                            dry_run=args.dry_run)

        import_models(config)


class PublishRunsController(cement.Controller):
    """ Publish runs of simulations of BiGG models to BioSimulations """

    class Meta:
        label = 'publish-runs'
        stacked_on = 'base'
        stacked_type = 'nested'
        help = "Publish runs of simulations to BioSimulations"
        description = "Publish runs of simulations of BiGG models to BioSimulations"
        arguments = []

    @ cement.ex(hide=True)
    def _default(self):
        config = get_config()
        biosimulators_config = get_biosimulators_config()

        # read simulation runs
        projects_filename = config['status_filename']
        with open(projects_filename, 'r') as file:
            projects = yaml.load(file, Loader=yaml.Loader)

        # check status
        failures = []
        for id, project in projects.items():
            if project['runbiosimulationsId']:
                response = requests.get(biosimulators_config.BIOSIMULATIONS_API_ENDPOINT + 'runs/' + project['runbiosimulationsId'])
                response.raise_for_status()
                project['runbiosimulationsStatus'] = response.json()['status']
                if project['runbiosimulationsStatus'] != 'SUCCEEDED':
                    failures.append('{}: {}'.format(id, project['runbiosimulationsStatus']))
            else:
                failures.append('{}: {}'.format(id, 'not submitted'))
        if failures:
            raise SystemExit('{} simulation runs did not succeed:\n  {}'.format(len(failures), '\n  '.join(sorted(failures))))

        # login to publish projects
        auth_headers = {
            'Authorization': biosimulators_utils.biosimulations.utils.get_authorization_for_client(
                config['biosimulations_api_client_id'], config['biosimulations_api_client_secret'])
        }

        # publish projects
        print('Publishing or updating {} projects ...'.format(len(projects)))
        for i_project, (id, project) in enumerate(projects.items()):
            print('  {}: {} ... '.format(i_project + 1, id), end='')
            sys.stdout.flush()

            endpoint = biosimulators_config.BIOSIMULATIONS_API_ENDPOINT + 'projects/' + id

            response = requests.get(endpoint)

            if response.status_code == 200:
                if response.json()['simulationRun'] == project['runbiosimulationsId']:
                    api_method = None
                    print('already up to date. ', end='')
                    sys.stdout.flush()

                else:
                    api_method = requests.put
                    print('updating ... ', end='')
                    sys.stdout.flush()

            else:
                api_method = requests.post
                print('publishing ... ', end='')
                sys.stdout.flush()

            if api_method:
                response = api_method(endpoint,
                                      headers=auth_headers,
                                      json={
                                          'id': id,
                                          'simulationRun': project['runbiosimulationsId']
                                      })
                response.raise_for_status()

            print('done.')
        print('')

        # print message
        print('All {} projects were successfully published or updated'.format(len(projects)))


class VerifyPublicationController(cement.Controller):
    """ Verify that models from BiGG have been successfully published to BioSimulations """

    class Meta:
        label = 'verify-publication'
        stacked_on = 'base'
        stacked_type = 'nested'
        help = "Verify that models have been published to BioSimulations"
        description = "Verify that models from BiGG have been successfully published to BioSimulations"
        arguments = []

    @ cement.ex(hide=True)
    def _default(self):
        config = get_config()
        biosimulators_config = get_biosimulators_config()

        # read BiGG projects
        bigg_projects_filename = config['status_filename']
        with open(bigg_projects_filename, 'r') as file:
            bigg_projects = yaml.load(file, Loader=yaml.Loader)

        # get BioSimulations projects
        biosimulations_api_endpoint = biosimulators_config.BIOSIMULATIONS_API_ENDPOINT
        response = requests.get(biosimulations_api_endpoint + 'projects')
        response.raise_for_status()
        biosimulations_projects = {
            project['id']: project
            for project in response.json()
        }

        # check all BiGG projects were published
        errors = []
        for bigg_project_id, bigg_project in bigg_projects.items():
            if bigg_project_id not in biosimulations_projects:
                if bigg_project['runbiosimulationsId']:
                    biosimulations_api_endpoint = biosimulators_config.BIOSIMULATIONS_API_ENDPOINT
                    response = requests.get(biosimulations_api_endpoint + 'runs/{}'.format(bigg_project['runbiosimulationsId']))
                    response.raise_for_status()
                    run_status = response.json()['status']
                else:
                    run_status = 'not submitted'
                errors.append('{}: has not been published. The status of run `{}` is `{}`.'.format(
                    bigg_project_id, bigg_project['runbiosimulationsId'], run_status))
            elif biosimulations_projects[bigg_project_id]['simulationRun'] != bigg_project['runbiosimulationsId']:
                biosimulations_api_endpoint = biosimulators_config.BIOSIMULATIONS_API_ENDPOINT
                url = biosimulations_api_endpoint + 'projects/{}'.format(bigg_project_id)
                response = requests.get(url)
                try:
                    response.raise_for_status()
                    owner = response.json().get('owner', {}).get('name', None)

                    if owner != 'BiGG':
                        reason = 'Project id has already been claimed.'
                    else:
                        reason = 'Project is published with run `{}`.'.format(response.json()['simulationRun'])
                except requests.exceptions.RequestException:
                    reason = 'Project could not be found'

                errors.append('{}: not published as run {}. {}'.format(bigg_project_id, bigg_project['runbiosimulationsId'], reason))

        # print message
        if errors:
            msg = '{} projects have been successfully published.\n\n'.format(len(bigg_projects) - len(errors))
            msg += '{} projects have not been successfully published:\n  {}'.format(len(errors), '\n  '.join(errors))
            raise SystemExit(msg)

        else:
            print('All {} projects have been successfully published.'.format(len(bigg_projects)))


class App(cement.App):
    """ Command line application """
    class Meta:
        label = 'biosimulations-bigg'
        base_controller = 'base'
        handlers = [
            BaseController,
            PublishController,
            PublishRunsController,
            VerifyPublicationController,
        ]


def main():
    with App() as app:
        app.run()
