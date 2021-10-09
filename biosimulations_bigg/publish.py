import os
import requests
import yaml


STATUS_FILENAME = os.path.join(os.path.dirname(__file__), 'final', 'status.yml')
BIOSIMULATIONS_API_ENDPOINT = 'https://api.biosimulations.org'
BIOSIMULATIONS_API_AUTH_ENDPOINT = 'https://auth.biosimulations.org/oauth/token'
BIOSIMULATIONS_API_AUDIENCE = 'dispatch.biosimulations.org'
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
        response = requests.get(BIOSIMULATIONS_API_ENDPOINT + '/runs/' + project['runbiosimulationsId'])
        response.raise_for_status()
        project['runbiosimulationsStatus'] = response.json()['status']
        if project['runbiosimulationsStatus'] != 'SUCCEEDED':
            failures.append('{}: {}'.format(id, project['runbiosimulationsStatus']))
    if failures:
        raise ValueError('{} simulation runs did not succeed:\n  {}'.format(len(failures), '\n  '.join(sorted(failures))))

    # login to publish projects
    response = requests.post(BIOSIMULATIONS_API_AUTH_ENDPOINT,
                             json={
                                 'client_id': BIOSIMULATIONS_API_CLIENT_ID,
                                 'client_secret': BIOSIMULATIONS_API_CLIENT_SECRET,
                                 'audience': BIOSIMULATIONS_API_AUDIENCE,
                                 "grant_type": "client_credentials",
                             })
    response.raise_for_status()
    response_data = response.json()
    auth_headers = {'Authorization': response_data['token_type'] + ' ' + response_data['access_token']}

    # publish projects
    for id, project in projects.items():
        response = requests.get(BIOSIMULATIONS_API_ENDPOINT + '/projects/' + id)

        if response.status_code == 200:
            if response.json()['simulationRun'] == project['runbiosimulationsId']:
                api_method = None
            else:
                api_method = requests.put
                endpoint = BIOSIMULATIONS_API_ENDPOINT + '/projects/' + id

        else:
            api_method = requests.post
            endpoint = BIOSIMULATIONS_API_ENDPOINT + '/projects'

        if api_method:
            response = api_method(endpoint,
                                  headers=auth_headers,
                                  json={
                                      'id': id,
                                      'simulationRun': project['runbiosimulationsId']
                                  })
            response.raise_for_status()

    # print message
    print('All {} projects were successfully published or updated'.format(len(projects)))


if __name__ == "__main__":
    main()
