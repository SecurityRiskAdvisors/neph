import re
import sys
import json
import pathlib
from typing import Optional, Literal
from pathlib import Path
from pydantic import BaseModel, Field, FilePath, NewPath
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    CliPositionalArg,
    get_subcommand,
    CliSubCommand,
    PydanticBaseSettingsSource,
    CliSettingsSource,
    CliApp,
    CliMutuallyExclusiveGroup,
)

OUTPUT_PARENT_PREFIX = "»"
OUTPUT_CHILD_PREFIX = "├"
OUTPUT_LAST_CHILD_PREFIX = "└"

# keeping imports in their respective subcommands to avoid issues where an import
# relies on the global settings. the root command needs the opportunity to override
# the settings before theyre used


class L2RPathCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="l2r")

    start: str = Field(description="Start node specifier")
    end: str = Field(description="End node specifier")
    add: bool = Field(default=False, description="Add a relation of the given type")
    # TODO: possibly move the promotion stuff to the leads cli
    #       then break into "leads add" and "leads manage"
    promote: bool = Field(default=False, description="Promote a lead of the given type")
    relation: Optional[str] = Field(default=None, description="Relationship type to add")

    def cli_cmd(self):
        from .path import add_l2r_path, get_l2r_paths, fmt_l2r_path_as_str, promote_l2r_leads

        if self.add:
            relation = self.relation.upper()
            add_l2r_path(start=self.start, end=self.end, relation=relation)
        elif self.promote:
            promote_l2r_leads(start=self.start, end=self.end, lead_type=self.relation)
        else:
            paths = get_l2r_paths(start=self.start, end=self.end)
            for path in paths:
                path_str = fmt_l2r_path_as_str(path)
                print(OUTPUT_PARENT_PREFIX, path_str)


class LeadsPathCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="leads")

    all: Optional[bool] = Field(default=False, description="Generate all lead types")
    node: Optional[str] = Field(default=None, description="Node type")
    lead: Optional[str] = Field(default=None, description="Lead type")

    def cli_cmd(self):
        from .nodes import get_node_by_label
        from .leads import generate_leads, leads, BaseLead, BaseLeadT
        from .utils import match_subclass
        from .settings import Settings

        # temporarily override the leads setting
        # as calling this subcommand should indicate the user
        # wants to generate leads
        original_leads_settings = Settings.generate_leads
        Settings.generate_leads = True

        if self.node:
            node_type = get_node_by_label(self.node)
            generate_leads(node_types=[node_type])

        elif self.lead:
            lead_cls: BaseLeadT = match_subclass(BaseLead, self.lead)
            lead_cls.populate()

        elif self.all:
            for lead in leads():
                lead.populate()

        Settings.generate_leads = original_leads_settings


class PathCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="path")

    l2r: CliSubCommand[L2RPathCli] = Field(description="Left-to-right paths")
    leads: CliSubCommand[LeadsPathCli] = Field(description="Leads generations")

    def cli_cmd(self):
        CliApp.run_subcommand(self)


class InspectCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="inspect")

    type: Literal["node", "edge", "enrichment", "fanout", "lead", "report"] = Field(description="Object type to list")

    def cli_cmd(self):

        args = {}
        match self.type:
            case "node":
                from .nodes import nodes

                fn = nodes
                args = {"include_fakes": False}

            case "edge":
                from .edges import edges

                fn = edges

            case "enrichment":
                from .enrich import enrichments

                fn = enrichments

            case "fanout":
                from .fanout import fanouts

                fn = fanouts

            case "lead":
                from .leads import leads

                fn = leads

            case "report":
                from .reporting import reports

                fn = reports

            case _:
                raise Exception(f'Unknown type: "{self.type}"')

        results = fn(**args)
        for result in results:
            output = result.__name__
            if self.type != "node":
                if result.__doc__:
                    docstring = result.__doc__.strip().replace("\n", " ")
                    docstring = re.sub("\\s+", " ", docstring)
                else:
                    docstring = ""
                output += f" : {docstring}"
            output = f"{OUTPUT_PARENT_PREFIX} {output}"
            print(output)


class CdcCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="cdc")

    def cli_cmd(self):
        from .cdc import start_cdc_server

        server = start_cdc_server()
        server.join()


class IngestCliJsonl(BaseModel):
    model_config = SettingsConfigDict(cmd_name="jsonl")

    manifest: Optional[FilePath] = Field(default=None, description="Path to manifest file")
    jsonl: Optional[FilePath] = Field(default=None, description="Path to JSONL file")
    table: Optional[str] = Field(default=None, description="Table name for direct file import")

    def cli_cmd(self):
        from .workflow import JsonlDataLoader

        if self.manifest:
            JsonlDataLoader.load(manifest_path=self.manifest)
        elif self.jsonl and self.table:
            JsonlDataLoader.load(table_name=self.table, jsonl_path=self.jsonl)


class IngestCliSql(BaseModel):
    model_config = SettingsConfigDict(cmd_name="sql")

    mode: Literal["bulk", "single"] = Field(description="Ingestion mode")
    create_fixtures: Optional[bool] = Field(default=True, description="For bulk mode, create fixture nodes")
    type: Optional[Literal["node", "table"]] = Field(
        default=None, description="For single mode, node type or Steampipe table to ingest"
    )
    target: Optional[str] = Field(default=None, description="For single mode, target node/table")

    def cli_cmd(self):
        from .nodes import get_node_by_table_name, get_node_by_label
        from .workflow import BulkSqlDataLoader

        if self.mode == "bulk":
            BulkSqlDataLoader.load(create_fixtures=self.create_fixtures)
        else:
            if self.type is None or self.target is None:
                raise Exception("Missing required CLI args")

            if self.type == "table":
                node = get_node_by_table_name(self.target)
            else:
                node = get_node_by_label(self.target)

            nodes = [node]
            BulkSqlDataLoader.load(create_fixtures=False, node_types=nodes)


class IngestCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="ingest")

    sql: CliSubCommand[IngestCliSql] = Field(description="SQL-based ingestion")
    jsonl: CliSubCommand[IngestCliJsonl] = Field(description="JSONL-based ingestion")

    def cli_cmd(self):
        CliApp.run_subcommand(self)


class SimCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="sim")

    principal: str = Field(description="Source principal ARN or service ID (e.g. ec2.amazonaws.com")
    action: str = Field(description="Action to simulate")
    resource: str = Field(default="*", description="Resource to target")
    raccount: Optional[str] = Field(default=None, description="Override resource account (assumes same as principal)")
    check_transitive: bool = Field(
        default=False,
        description="Also run simulation for roles the principal can assume (does not apply to service principals).",
    )

    org_policies: bool = Field(
        default=False, description="Include AWS Organizations policies (SCPs/RCPs) in simulation"
    )

    write: bool = Field(default=False, description="Write result to graph")

    def cli_cmd(self):
        from .sim import iam_principal_can_perform, service_can_perform

        service_principal = False
        if self.principal.endswith(".amazonaws.com"):
            service_principal = True

        if service_principal:
            fn = service_can_perform
            # override this for SPs
            self.check_transitive = False
        else:
            fn = iam_principal_can_perform

        result = fn(
            principal=self.principal,
            action=self.action,
            resource=self.resource,
            resource_account=self.raccount,
            include_org_policies=self.org_policies,
            write_to_graph=self.write,
            check_transitivity=self.check_transitive,
        )

        transitive_arns = None
        if not service_principal:
            result, transitive_arns = result

        dodonot = "can" if result else "cannot"
        print(f'{OUTPUT_PARENT_PREFIX} "{self.principal}" {dodonot} perform "{self.action}" against "{self.resource}"')

        if transitive_arns:
            for transitive_arn in transitive_arns:
                print(
                    f'{OUTPUT_PARENT_PREFIX*2} "{transitive_arn}" can perform "{self.action}" against "{self.resource}"'
                )


class ExporterCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="exporter")

    manifest: Path = Field(description="Path to output manifest")
    script: Path = Field(description="Path to output shell script")
    export: Literal["nodes"] = Field(default="nodes", description="Data export type")
    format: Literal["query", "standalone"] = Field(default="standalone", description="Export command format")

    def cli_cmd(self):
        from .jsonl import generate_standalone_export_commands, ExportCommandFormat

        if self.export == "nodes":
            cmd_format = ExportCommandFormat(self.format)
            manifest, script = generate_standalone_export_commands(cmd_format=cmd_format)
            self.manifest.write_text(json.dumps(manifest, indent=4))
            self.script.write_text(script)


class BaseWorkflowCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="baseworkflow")

    node: str = Field(description="Node type")

    def cli_cmd(self):
        from .workflow import BaseNodeWorkflow
        from .nodes import get_node_by_label

        node_type = get_node_by_label(self.node, include_fakes=True)

        BaseNodeWorkflow.analyze(node=node_type)


class WorkflowCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="workflows")

    base: CliSubCommand[BaseWorkflowCli] = Field(description="Base workflow")

    def cli_cmd(self):
        CliApp.run_subcommand(self)


class FanoutCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="fanout")

    arn: str = Field(description="Source principal ARN")
    strategy: str = Field(description="Fanout strategy name")

    include_resources: bool = Field(
        default=True, description="For permissions strategies, include resource ARN templates for each returned action"
    )

    def cli_cmd(self):
        from .utils import match_subclass
        from .fanout import (
            PermissionsFanout,
            FanoutStrategy,
            ServicesFanout,
            fanout_principal,
            FanoutStrategyT,
            BruteForceFanout,
        )
        from .aws.resources import get_details_for_action
        from .settings import Settings

        # TODO: remove parent classes
        target_strategy: FanoutStrategyT = match_subclass(FanoutStrategy, self.strategy)

        results = fanout_principal(principal_arn=self.arn, strategy=target_strategy)
        if issubclass(target_strategy, PermissionsFanout):
            if not self.include_resources:
                print("\n".join(results))
            else:
                # TODO: wrap this styling in a utility function
                for action in results:
                    print(f"{OUTPUT_PARENT_PREFIX} {action}")
                    details_list = get_details_for_action(action)
                    for i, (resource, details) in enumerate(details_list):
                        if arn := details.get("arn", None):
                            prefix = OUTPUT_LAST_CHILD_PREFIX if len(details_list) == i + 1 else OUTPUT_CHILD_PREFIX
                            print(f"  {prefix} {arn}")
                    print()
        elif issubclass(target_strategy, ServicesFanout):
            results = sorted(results)
            for result in results:
                service_name = (
                    Settings.iam_data.services.get_service_name(result)
                    if Settings.iam_data.services.service_exists(result)
                    else "UNKNOWN"
                )
                print(f"{service_name} [{result}]")
        elif issubclass(target_strategy, BruteForceFanout):
            for arn, outcome in results:
                if outcome:
                    print(f"{arn} -> {outcome}")
        else:
            # TODO: add post-processing to strategy class
            pass


class MiscDbCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="misc")

    connections: bool = Field(default=True, description="Print number of connections not yet ready for use")

    def cli_cmd(self):
        from .db import connections_not_ready

        if self.connections:
            conn_ct = connections_not_ready()
            if conn_ct > 0:
                print(f"Awaiting {conn_ct} connections")
            else:
                print("All connections ready!")


class MiscCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="misc")

    db: CliSubCommand[MiscDbCli] = Field(description="Steampipe database utils")

    def cli_cmd(self):
        CliApp.run_subcommand(self)


class ReportCli(BaseModel):
    model_config = SettingsConfigDict(cmd_name="report")

    format: Literal["csv"] = Field(default="csv", description="Report format")
    outfile: NewPath | FilePath = Field(description="Path to output file")
    report: str = Field(description="Report to run")

    def cli_cmd(self):
        from .reporting import property_table_as_csv, PropertiesTable, PropertiesTableT
        from .utils import match_subclass

        report_cls: PropertiesTableT = match_subclass(PropertiesTable, self.report)
        match self.format:
            case "csv":
                csv_str = property_table_as_csv(report_cls)
                pathlib.Path(self.outfile).write_text(csv_str)
            case _:
                pass


class Cli(
    BaseSettings,
    cli_prog_name="neph",
    cli_kebab_case=True,
    cli_avoid_json=True,
    cli_implicit_flags=True,
    cli_hide_none_type=True,
    cli_parse_args=True,
):
    settings: Optional[FilePath] = Field(default=None, description='Override default (".env") settings file')
    load_plugins: bool = Field(default=True, description="Load 3rd-party plugins")

    cdc: CliSubCommand[CdcCli] = Field(description="Configure the workflow trigger listener")
    ingest: CliSubCommand[IngestCli] = Field(description="Data loading")
    sim: CliSubCommand[SimCli] = Field(description="Request simulation")
    exporter: CliSubCommand[ExporterCli] = Field(description="Steampipe exporter generator")
    workflow: CliSubCommand[WorkflowCli] = Field(description="Workflow management")
    misc: CliSubCommand[MiscCli] = Field(description="Misc utils")
    fanout: CliSubCommand[FanoutCli] = Field(description="Fanout discovery")
    report: CliSubCommand[ReportCli] = Field(description="Report generation")
    inspect: CliSubCommand[InspectCli] = Field(description="Class inspection utilities")
    path: CliSubCommand[PathCli] = Field(description="Path management")

    def cli_cmd(self):
        if self.settings:
            from .settings import Settings, SettingsCls

            new_settings = SettingsCls.from_envf(self.settings)
            Settings.update(new_settings)

        if self.load_plugins:
            from .plugins import load_all_plugins

            load_all_plugins()

        from .db import verify_neo4j_connection

        verify_neo4j_connection()

        from .utils import load_graph_classes

        load_graph_classes()

        CliApp.run_subcommand(self)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            CliSettingsSource(settings_cls, cli_parse_args=True),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


def main():
    CliApp.run(Cli, cli_args=sys.argv)


if __name__ == "__main__":
    main()
