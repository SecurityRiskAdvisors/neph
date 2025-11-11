# Misc Cypher Queries

Example Cypher queries

Notes:
- Queries containing IAM policy nodes also work for inline policy nodes (change `IamPolicy` to `IamInlinePolicy` or use both `IamPolicy|IamInlinePolicy`)
- More involved analysis examples can be found in the JupyterLab's included query notebook (sourced from [here](../dockerfiles/jupyter/queries.md))

### Leads for account X

```
MATCH p=(n)-[r:LEAD]->(m{account_id:"123456789012"})
WHERE not n:Service
RETURN p
```

- there WHERE is optional

### General leads summaries

Break down leads of a given type (exampe: `CAN_ASSUME`)

```
MATCH p=(n)-[:LEAD{type:"CAN_ASSUME"}]->(m) 
WITH labels(n)[0] as start, labels(m)[0] as end
RETURN start, end, count(*)
```

### Direct admin policy attachments

```
MATCH (n:IamPolicy{name:"AdministratorAccess"})-[r:ATTACHED]->(m)
RETURN m.arn, m.account_id
```

### Node count by account

```
MATCH (n)
WITH count(n.account_id) as ct, n.account_id as id ORDER BY ct desc
RETURN ct, id
```

### Label stats

```
CALL apoc.meta.stats()
YIELD labels
RETURN labels
```

### Objects with direct privesc permissions in custom policies

```
MATCH p=(n)<-[:ATTACHED]-(m:IamPolicy)
WHERE toBoolean(m.is_aws_managed) = FALSE and toBoolean(m.iam_privesc) = TRUE
RETURN p
```

### EC2 instances with instance profiles that have privesc managed policies attached

```
MATCH p=(policy:IamPolicy)-[:ATTACHED]->(:IamRole)<-[:INSTANCE_PROFILE]-(:IamInstanceProfile)<-[:CAN_ASSUME]-(:EC2Instance)
WHERE toBoolean(policy.iam_privesc) = TRUE
RETURN p
```

### Large service count in customer-managed IAM policy

```
MATCH (n:IamPolicy|IamInlinePolciy)
WITH *, toInteger(n.num_services) as num_services
WHERE toBoolean(n.is_aws_managed)=FALSE and num_services > 20
RETURN n.arn, n.num_services ORDER BY num_services DESC
```

Replace `20` with your number of choice

### Account-level role trust leads

```
MATCH p=(n:Account)-[:LEAD{type:"CAN_ASSUME"}]->(m:IamRole)
RETURN p
```

### Specific abusable permissions in role policy

```
MATCH (role:IamRole)<-[:ATTACHED]-(policy)
WITH *, apoc.convert.fromJsonList(policy.iam_privesc_permissions) as permissions
WHERE toBoolean(policy.iam_privesc)=TRUE and "iam:CreateAccessKey" in permissions 
RETURN role.arn, permissions, policy.arn
```

Replace `iam:CreateAccessKey` with the permission of interest


### Role with all permissions for service ("service admin")

```
MATCH (role:IamRole)<-[:ATTACHED]-(policy)
WITH *, apoc.convert.fromJsonList(policy.service_admin) as services
WHERE "ec2" in services 
RETURN role.arn, permissions, policy.arn
```

Replace `ec2` with the service of interest
