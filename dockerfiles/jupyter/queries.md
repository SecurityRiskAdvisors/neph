---
jupytext:
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
---

# Configuration

Run this cell once to configure the Notebook

```{code-cell}
import pathlib
import pandas as pd
from yfiles_jupyter_graphs_for_neo4j import Neo4jGraphWidget
from neo4j import GraphDatabase
from neph.settings import SettingsCls, Settings
from neph.db import session

pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', None)
Settings.update(SettingsCls.from_envf(pathlib.Path("/notebooks/.env")))
Settings._settings.neo4j_host = "neo4j"
Settings._settings.simulator_url = "http://simulator:3000/"
driver = GraphDatabase.driver(Settings.neo4j_url, auth=(Settings.neo4j_user, Settings.neo4j_password))
g = Neo4jGraphWidget(driver)

def query_as_df(query):
    with session() as s:
        results = s.run(query).values()
    return pd.DataFrame(data=results)
```

- if you change the env file mount in your Compose file, you also need replace `/notebooks/.env` above 
- if you change the Compose service host names, you also need to modify `neo4j_host = "neo4j"` and `simulator_url = "http://simulator:3000/"` 
- you can remove the `pd.set_option('display.max_rows', None)` line prior to running to truncate DataFrame output 

# General use

To return a Graph inside the notebook, do 

```{code-cell}
g.show_cypher("<Cypher query>")
```

To return a non-graph query result, such a table, use a Pandas DataFrame like:

```{code-cell}
query_as_df("<Cypher query>")
```

# EC2-EC2 Lateral Movement

This section describes how to look for EC2-EC2 lateral movement via SSM/EC2 Instance Connect. These services provide alternative access mechanisms to EC2 instances.

First, identify candidate EC2 instances.
This query looks for EC2 instances with an instance profile then returns the underlying IAM role ARN.

```{code-cell}
query = """
MATCH p=(n:EC2Instance)-[r:CAN_ASSUME]->(:IamInstanceProfile)-[:INSTANCE_PROFILE]->(m:IamRole) RETURN distinct m.arn
"""
ec2lm_df = query_as_df(query)
ec2lm_df
```

+++

To store the ARNs directly:

```{code-cell}
ec2_role_arns = [result for result in ec2lm_df[0]]
```

+++

Then, using those IAM roles, filter to only those with SSM/EC2 Instance Connect permissions in their identity policies.
This is done using the EC2AccessFanout.
The below snippet will run the fanout for each ARN and print the ARNs that had at least one relevant permission.

```{code-cell}
from neph.fanout import fanout_principal
from neph.aws.other.fanouts import EC2AccessFanout

for arn in ec2_role_arns:
    fanout_result = fanout_principal(principal_arn=arn, strategy=EC2AccessFanout)
    if len(fanout_result) > 0:
        print(arn, fanout_result)
```

Finally, you can run results through the Simulator to determine if the role can actually perform the action (fill in `principal` and `action` based on above output).

```{code-cell}
from neph.sim import iam_principal_can_perform
iam_principal_can_perform(
    principal=<arn>,
    action=<action>,
    resource="*",
    include_org_policies=True,
    write_to_graph=False,
)
```

# Role privilege escalation

This section describes how to look for role privilege escalation.
Specifically, it uses the "iam_privesc" policy node enrichment, which is a property added to policy nodes that include an abusable privilege.

To look for roles without a privesc permission that can assume a role with privesc permission:

```{code-cell}
query = """
match (low:IamRole)
where count{ (pol{iam_privesc:"true"})-[:ATTACHED]->(low) } = 0
match (pol2)-[:ATTACHED]->(high:IamRole) 
where toBoolean(pol2.iam_privesc)=TRUE
match p=(low)-[:LEAD{type:"CAN_ASSUME"}]->(high)
return p
"""
g.show_cypher(query)
```

You can also add the the condition `toBoolean(pol2.is_aws_managed)=FALSE` to the second match statements to further limit results to only policies that both have an abusable permission and are customer-managed (e.g. exclude AWS-managed policies).

This query uses the `CAN_ASSUME` to determine role-role assumption. Since this is a lead, you should further analyze the trust policy for the target role.

# Confused Deputies

Confused deputies attack paths arise when you can indirectly perform an action by influencing another principal to perform that action for you. For example, by triggering a service to interact with another service. This allows you to leverage the permissions of the influence-able principal (the "deputy").

To look for confused deputies, look for leads where the starting node is a Service node. In this example, its specifically looking at the `CAN_INTERACT` lead, but you can also use other lead types, like `CAN_ASSUME`.

```{code-cell}
query = """
match p=(n:Service)-[:LEAD{type:"CAN_INTERACT"}]->(m) 
where m.policy is not null
with n.key as key, labels(m)[0] as end
return key, end, count(*)
"""
query_as_df(query)
```

This will return a list of how many relationships exist for each service-resource pair after filtering for resources with resource policies.

*Note: Steampipe typically includes resource policies under the `policy` column. But some tables may differ.*  

The main thing to analyze is the resource policy of the destination node. 
Specifically, look for statements where the principal is a service and does not have condition keys to restrict the 
principal, such as `aws:SourceAccount`.

# Tiering Violations

In an AWS Organization, the Organization master account should be treated as a tier-0 asset as it has privileged access
to all other accounts in the Organization. Generally, principals should not be allowed access to the Master account
outside of restricted administrator principals. 

You should look for paths into the Organization master account. To do so, first identify these accounts.
This can be done by looking for `Organization` nodes and/or by looking at the `organization_master_account_id` property of the `Account` nodes.
Note: the `Account` nodes are populated by querying for account details for each connection in the Steampipe configuration.
However, some relationship building queries will create stubbed versions of these nodes containing only the account ID.
For example, the trust policy lead will look for accounts trusted to assume roles.
These stubbed nodes will not have the `organization_master_account_id` property.
Note: It is possible that there are multiple Organizations in your data set, depending on the environment.

Once you have an Organization master, you can look for paths towards resources in that account
then investigate the results

```{code-cell}
query = """
match p=(n)-[]->(m)
where m.account_id = "<master account>" and n.account_id <> "<master account>"
return p
"""
g.show_cypher(query)
```

# External account references

To look for nodes with references to external accounts in their resource policies, you can use the `ExternalAccountReferences` report.
This report will look for any node with a resource policy (`policy` or `assume_role_policy` property) then do a regex extraction for 12-digit values. 
For any match, it compares it against the list of account IDs in the organization (using the `OrganizationAccount` nodes).

```{code-cell}
from neph.aws.nodes.core import ExternalAccountReferences 
report = ExternalAccountReferences.report()
pd.DataFrame(data=report)
```

This will return a table of the node, the external account, and the resource policy. It is equivalent to running `neph report --format csv --report ExternalAccountReferences ...` from the Neph CLI.

Results should then be verified manually.

