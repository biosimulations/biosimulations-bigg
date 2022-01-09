from biosimulations_bigg import __main__
from biosimulations_bigg._version import __version__
from biosimulations_bigg.core import import_models
from biosimulations_bigg.config import get_config
from unittest import mock
import Bio.Entrez
import biosimulations_bigg.__main__
import capturer
import os
import requests_cache
import shutil
import tempfile
import unittest

Bio.Entrez.email = 'biosimulations.daemon@gmail.com'


class MockCrossRefSessionResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            'message': {
                'title': [''],
                'container-title': [''],
                'volume': '',
                'published': {
                    'date-parts': [
                        [
                            2021,
                            12,
                            31,
                        ]
                    ]
                }
            }
        }


class MockCrossRefSession:
    def get(self, url):
        return MockCrossRefSessionResponse()


class MockS3Bucket:
    def __init__(self, name):
        pass

    def upload_file(self, *args, **kwargs):
        pass


class TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirname = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dirname)

    def test_import_models(self):
        config = get_config(
            source_dirname=os.path.join(self.dirname, 'source'),
            sessions_dirname=os.path.join(self.dirname, 'source'),
            final_dirname=os.path.join(self.dirname, 'final'),
            status_filename=os.path.join(self.dirname, 'final', 'status.yml'),
            max_models=1,
            max_num_reactions=200,
            bucket_name='bucket',
        )

        config['cross_ref_session'] = MockCrossRefSession()

        with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
            with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
                with mock.patch('boto3.resource', return_value=mock.Mock(Bucket=MockS3Bucket)):
                    import_models(config)

    def test_cli(self):
        with mock.patch.dict('os.environ', {
            'SOURCE_DIRNAME': os.path.join(self.dirname, 'source'),
            'SESSIONS_DIRNAME': os.path.join(self.dirname, 'source'),
            'FINAL_DIRNAME': os.path.join(self.dirname, 'final'),
            'STATUS_FILENAME': os.path.join(self.dirname, 'final', 'status.yml'),
            'BUCKET_NAME': 'bucket',
        }):
            def mock_get_config(**args):
                config = get_config(**args)
                config['cross_ref_session'] = MockCrossRefSession()
                return config

            with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
                with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
                    with mock.patch('boto3.resource', return_value=mock.Mock(Bucket=MockS3Bucket)):
                        import biosimulations_bigg.config
                        with mock.patch.object(biosimulations_bigg.__main__, 'get_config', side_effect=mock_get_config):
                            with __main__.App(argv=[
                                'publish',
                                '--max-models', '1',
                                '--max-num-reactions', '200',
                            ]) as app:
                                app.run()

    def test_cli_help(self):
        with mock.patch('sys.argv', ['', '--help']):
            with self.assertRaises(SystemExit):
                __main__.main()

    def test_version(self):
        with __main__.App(argv=['--version']) as app:
            with capturer.CaptureOutput(merged=False, relay=False) as captured:
                with self.assertRaises(SystemExit) as cm:
                    app.run()
                    self.assertEqual(cm.exception.code, 0)
                stdout = captured.stdout.get_text()
                self.assertEqual(stdout, __version__)
                self.assertEqual(captured.stderr.get_text(), '')
