Tutorial
========

First, set the following environment variables

* ``ENTREZ_EMAIL``: email address to credit queries to NCBI Entrez to (e.g., ``biosimulations.daemon@gmail.com``)
* ``BIOSIMULATIONS_API_CLIENT_ID``: id of the client for the BioSimulations API
* ``BIOSIMULATIONS_API_CLIENT_SECRET``: secret for this client
* ``BUCKET_ENDPOINT``: Endpoint for uploading COMBINE/OMEX archives to be published to an S3 bucket
* ``BUCKET_NAME``: Name of the bucket
* ``BUCKET_ACCESS_KEY_ID``: Access key for the bucket
* ``BUCKET_SECRET_ACCESS_KEY``: Secret for the access key

Second, to optionally use `Gurobi <https://www.gurobi.com/products/gurobi-optimizer/>`_ to execute simulations, encode your Gurobi license into environment variables prefixed with ``GRB_``. For example, to use Gurobi with a `Web License Service <https://www.gurobi.com/academia/academic-program-and-licenses/>`_ set these environment variables:

* ``GRB_LICENSEID``: license id
* ``GRB_WLSACCESSID``: access id
* ``GRB_WLSSECRET``: secret

Third, run the following command-line program to published the models in the BiGG repository to BioSimulations. This program downloads models from BiGG, converts them to COMBINE/OMEX archives, submits the archives to runBioSimulations, and publishes their simulation runs to BioSimulations. This program provides several optional arguments for forcing updates, skipping simulations, skipping publication, and more.::

   biosimulations-bigg publish

Fourth, the following command-line program can optionally be run to publish the runs of each model to BioSimulations. This is useful if the above publication program was run with the ``--skip-publication`` option.::

   biosimulations-bigg publish-runs

Fifth, run the following command-line program to verify that each model was successfully published to BioSimulations. This should be run several minutes after the publication step was run.::

   biosimulations-bigg verify-publication

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
#. Uses `BioSimulators-COBRApy <https://github.com/biosimulators/Biosimulators_COBRApy>`_ to test the execution the COMBINE/OMEX archive.
#. Checks that the optimal objective value is positive.
#. Submits the COMBINE/OMEX archive to runBioSimulations.
#. Publishes the run of the archive to BioSimulations. 
#. Updates the import status of the model in ``biosimulations_bigg/final/status.yml``
