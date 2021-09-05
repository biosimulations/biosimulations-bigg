Tutorial
========

The models in the BiGG repository can be imported in BioSimulations by running the command-line program as illustrated below::

   biosimulations-bigg

Help for the command-line program is available inline by running::

   biosimulations-bigg --help

The command-line program imports each BiGG models into BioSimulations as follows:

#. Checks ``biosimulations_bigg/final/issues.yml`` for any known issues about the model which prevent it from being imported in BioSimulations (e.g., the files are not valid SBML or no reference is available). Issues with models should be reported using the `BiGG issue tracker <https://github.com/SBRG/bigg_models/issues>`_.
#. Checks the import status of the model in ``biosimulations_bigg/final/status.yml`` and determines whether the model hasn't yet been imported into BioSimuations or needs to be re-imported because it has been updated in BiGG since it was imported into BioSimulations.
#. Retrieves the model and metadata about the model from BiGG.
#. If applicable, retrieves `Escher <https://escher.github.io/>`_ flux maps for the model from BiGG.
#. Uses `PubMed <https://pubmed.ncbi.nlm.nih.gov/>`_ and `CrossRef <https://crossref.org/>`_ to get information about the publication cited for the model.
#. If possible, uses the `open access subset of PubMed Central <https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/>`_ to retrive thumbnail images for the model.
#. Creates a `Simulation Experiment Description Markup Langauge <http://sed-ml.org/>`_ (SED-ML) file which describes a flux balance analysis simulation of the model.
#. Converts the Escher flux maps to `Vega <https://vega.github.io/vega/>`_ data visualizations.
#. Exports the metadata to a OMEX metadata-compliant RDF file. The list of curators is determined by ``biosimulations_bigg/final/curators.yml``. Individuals who contribute should add their name to this document.
#. Packages the model, SED-ML, Escher and Vega flux maps, images, and metadata files into a `COMBINE/OMEX archive <https://combinearchive.org/>`_.
#. Uses `BioSimultors-COBRApy <https://github.com/biosimulators/Biosimulators_COBRApy>`_ to execute the COMBINE/OMEX archive.
#. Checks that the optimal objective value is positive.
#. Submits the COMBINE/OMEX archive to RunBioSimulations.
#. Updates the import status of the model in ``biosimulations_bigg/final/status.yml``
