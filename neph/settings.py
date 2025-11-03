import csv
from pathlib import Path
from importlib.resources import path as resource_path
from functools import cached_property
from iamdata import IAMData
from pydantic_settings import BaseSettings, SettingsConfigDict, DotEnvSettingsSource
from typing import List, Self

# TODO: https://hitchdev.com/strictyaml/


# tables likely requiring permissions in org root account
AWS_ORG_TABLES = [
    "aws_organizations_policy",
    "aws_organizations_root",
    "aws_organizations_account",
    "aws_organizations_policy_target",
    "aws_organizations_organizational_unit",
    "aws_ssoadmin_managed_policy_attachment",
    "aws_ssoadmin_permission_set",
    "aws_ssoadmin_instance",
    "aws_ssoadmin_account_assignment",
    "aws_identitystore_user",
    "aws_identitystore_group",
    "aws_identitystore_group_membership",
]


DotEnvKwargs = {"env_file": ".env", "env_prefix": "NEPH_", "case_sensitive": False}


class SettingsCls(BaseSettings):
    model_config = SettingsConfigDict(**DotEnvKwargs)

    # Neo4j connection info
    neo4j_host: str = "localhost"
    neo4j_port: str = "7687"
    neo4j_proto: str = "bolt"  # or bolt
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4neo4"
    neo4j_db: str = "neo4j"

    # for SQL-in-Cypher queries that use batching, this
    # will control the batch size
    jdbc_batch_size: int = 1000

    # Steampipe connection info
    steampipe_host: str = "localhost"
    steampipe_port: str = "9193"
    steampipe_user: str = "steampipe"
    # steampipe doesnt support configuring a password via the config
    # but you if you write it to a file at `internal/.passwd` in the
    # install directory, it will use it
    steampipe_password: str = "0ab0_439a_9775"
    # you can use the aggregator to group steampipe connections via an
    # aggregation function
    # if you are using an aggregator, you can target individual accounts
    # by setting the aggregator to the connection name
    # e.g. if you want to perform ingestion on an individual basis
    #      while still using the aggregator in the config
    steampipe_aggregator: str = "aws"

    simulator_url: str = "http://simulator:3000/"

    # log file configs
    # the CDC uses its own log file as it will typically run
    # in a separate context than a CLI client
    log_file: str = ".neph.log"
    log_level: str = "info"
    cdc_log_file: str = ".neph_cdc.log"

    # CDC API server config shared by the API server and
    # the trigger
    cdc_trigger: str = "neph_cdc"  # shouldve called it iblis
    cdc_host: str = "localhost"
    cdc_proto: str = "http"
    cdc_uri: str = "/cdc"
    cdc_port: int = 9003
    use_cdc: bool = False

    # exclude edges/nodes (and only edges/nodes) from aggregation functions
    # (nodes(), edges()) if their table(s) are in AWS_ORG_TABLES
    # does not affect direct calls to those edges/nodes nor their methods
    load_aws_org: bool = False

    # optionally disable lead generation
    # note: does not prevent running individual leads by
    #       calling their populate() method
    #       only affects the generate_leads() bulk calls
    # This defaults to false for performance reasons
    #   larger environments can take a while
    #   For larger environments, disable leads generation
    #       then run the leads CLI after ingestion completes
    generate_leads: bool = False

    @property
    def cdc_url(self) -> str:
        return f"{self.cdc_proto}://{self.cdc_host}:{self.cdc_port}{self.cdc_uri}"

    @cached_property
    def iam_data(self) -> IAMData:
        return IAMData()

    @property
    def neo4j_url(self):
        return f"{self.neo4j_proto}://{self.neo4j_host}:{self.neo4j_port}/{self.neo4j_db}"

    @property
    def steampipe_jdbc_url(self) -> str:
        return f"jdbc:postgresql://{self.steampipe_host}:{self.steampipe_port}/steampipe?user={self.steampipe_user}&password={self.steampipe_password}"

    @cached_property
    def steampipe_tables_schema(self) -> dict:
        # CSV is a dump of the Steampipe table schemas
        # which can be retrieved like:
        #
        #   copy(
        #       select
        #           table_name as table,
        #           array_agg(column_name) as columns
        #       from information_schema.columns
        #       where table_name like 'aws_%'
        #       group by table_name
        #   ) to stdout with csv header
        #
        # redirected to the `<neph>/data/columns.txt` file
        # TODO: add Makefile target to generate this
        #       ./steampipe --install-dir <dir> query --output csv export.sql > <outfile>
        #           where export.sql is the above sql (without the copy)
        with resource_path("neph", "data") as p:
            csvfile = p / "columns.txt"
            data = {}
            with csvfile.open() as csvfd:
                reader = csv.reader(csvfd)
                for row in reader:
                    cols = row[1][1 : len(row[1]) - 1].split(",")
                    data[row[0]] = cols
        return data

    @property
    def aws_org_tables(self) -> List[str]:
        return AWS_ORG_TABLES

    # based on https://github.com/pydantic/pydantic-settings/issues/259#issuecomment-2354237980
    @classmethod
    def from_envf(cls, path: Path) -> Self:
        kwargs = {**DotEnvKwargs, "env_file": path}
        return cls(**DotEnvSettingsSource(cls, **kwargs)())


# tbh I dont like this but it makes it easy for other components to edit the global settings
# will definitely revisit this later
# TODO: a better approach for the future would be to implement a diffing update on the
#       main SettingsCls or some other in-place change mechanism (using another SettingsCls instance)
class SettingsProxy:
    def __init__(self):
        self._settings = SettingsCls()

    def update(self, o: SettingsCls):
        self._settings = o

    def __getattr__(self, item):
        return getattr(self._settings, item)


Settings = SettingsProxy()
