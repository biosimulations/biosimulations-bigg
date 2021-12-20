from biosimulators_utils.config import Config
import biosimulators_utils.biosimulations.utils
import os
import requests
import sys
import yaml


STATUS_FILENAME = os.path.join(os.path.dirname(__file__), 'final', 'status.yml')
BIOSIMULATIONS_API_ENDPOINT = Config().BIOSIMULATIONS_API_ENDPOINT
BIOSIMULATIONS_API_CLIENT_ID = os.getenv('BIOSIMULATIONS_API_CLIENT_ID')
BIOSIMULATIONS_API_CLIENT_SECRET = os.getenv('BIOSIMULATIONS_API_CLIENT_SECRET')


def main():
    # read simulation runs
    projects_filename = STATUS_FILENAME
    with open(projects_filename, 'r') as file:
        projects = yaml.load(file, Loader=yaml.Loader)

    # check status
    failures = []
    for id, project in projects.items():
        response = requests.get(BIOSIMULATIONS_API_ENDPOINT + 'runs/' + project['runbiosimulationsId'])
        response.raise_for_status()
        project['runbiosimulationsStatus'] = response.json()['status']
        if project['runbiosimulationsStatus'] != 'SUCCEEDED':
            failures.append('{}: {}'.format(id, project['runbiosimulationsStatus']))
    if failures:
        raise ValueError('{} simulation runs did not succeed:\n  {}'.format(len(failures), '\n  '.join(sorted(failures))))

    # login to publish projects
    auth_headers = {
        'Authorization': biosimulators_utils.biosimulations.utils.get_authorization_for_client(
            BIOSIMULATIONS_API_CLIENT_ID, BIOSIMULATIONS_API_CLIENT_SECRET)
    }

    # publish projects
    print('Publishing or updating {} projects ...'.format(len(projects)))
    for i_project, (id, project) in enumerate(projects.items()):
        print('  {}: {} ... '.format(i_project + 1, id), end='')
        sys.stdout.flush()

        endpoint = BIOSIMULATIONS_API_ENDPOINT + 'projects/' + id

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

    # print message
    print('All {} projects were successfully published or updated'.format(len(projects)))


if __name__ == "__main__":
    main()
