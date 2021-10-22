from .core import import_models, get_config
import argparse


def main():
    parser = argparse.ArgumentParser(description='Import models from BiGG into BioSimulations')
    parser.add_argument('--max-models', type=int, default=None,
                        help='Maximum number of models to import. Used for testing.')
    parser.add_argument('--max-num-reactions', type=int, default=None,
                        help='Maximum size model to import. Used for testing.')
    parser.add_argument('--update', action='store_true',
                        help='If set, update models even if they have already been imported.')
    parser.add_argument('--skip-simulation', action='store_true',
                        help='If set, do not simulate models. Used for testing.')
    parser.add_argument('--dry-run', action='store_true',
                        help='If set, do not submit models to BioSimulations. Used for testing.')

    args = parser.parse_args()

    config = get_config(max_models=args.max_models, max_num_reactions=args.max_num_reactions,
                        update=args.update,
                        simulate_models=not args.skip_simulation,
                        dry_run=args.dry_run)

    import_models(config)
