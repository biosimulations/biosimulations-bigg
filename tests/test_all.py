from biosimulations_bigg import __main__
from biosimulations_bigg._version import __version__
from biosimulations_bigg.core import import_models, get_config
from unittest import mock
import Bio.Entrez
import capturer
import os
import shutil
import tempfile
import unittest

Bio.Entrez.email = 'biosimulations.daemon@gmail.com'


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
        )
        with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
            with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
                import_models(config)

    def test_cli(self):
        with mock.patch.dict('os.environ', {
            'SOURCE_DIRNAME': os.path.join(self.dirname, 'source'),
            'SESSIONS_DIRNAME': os.path.join(self.dirname, 'source'),
            'FINAL_DIRNAME': os.path.join(self.dirname, 'final'),
            'STATUS_FILENAME': os.path.join(self.dirname, 'final', 'status.yml'),
        }):
            with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
                with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
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
