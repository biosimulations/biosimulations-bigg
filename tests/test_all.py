from biosimulations_bigg.__main__ import main
from biosimulations_bigg.core import import_models, get_config
from unittest import mock
import Bio.Entrez
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
            final_dirname=os.path.join(self.dirname, 'final'),
            status_filename=os.path.join(self.dirname, 'final', 'status.yml'),
            max_models=1,
            max_num_reactions=200,
        )
        with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
            with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
                import_models(config)

    def test_cli(self):
        with mock.patch('biosimulators_utils.biosimulations.utils.run_simulation_project', return_value='*' * 32):
            with mock.patch('biosimulators_utils.biosimulations.utils.get_authorization_for_client', return_value='xxx yyy'):
                with mock.patch('sys.argv', ['', '--max-models', '1', '--max-num-reactions', '200']):
                    main()

    def test_cli_help(self):
        with mock.patch('sys.argv', ['', '--help']):
            with self.assertRaises(SystemExit):
                main()
