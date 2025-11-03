# Neph Overview

## Components

Neph is an AWS attack path graphing tool. 

Neph is compromised of several components:

- The graph database, [Neo4j](https://neo4j.com/)
- The AWS resource collector, [Steampipe](https://steampipe.io/)
- The IAM simulator, [iam-simulate](https://github.com/cloud-copilot/iam-simulate)
- The controller, Neph

## Deploy

To deploy Neph, you can use the included example Docker Compose file as a reference. 
It should be run from the root of the Neph project repo after updating the mounts and environment variables to the preferred values.
Refer to the [quickstart guide](Quickstart.md) for getting started.
