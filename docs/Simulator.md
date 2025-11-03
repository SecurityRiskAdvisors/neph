# IAM Simulation

Neph uses a local IAM simulator to determine if a principal can perform an action then, if it can, persist that 
data to the graph as a relationship.

Neph uses the [iam-simulate](https://github.com/cloud-copilot/iam-simulate) project to perform this analysis. 
This project analyzes the provided IAM policy information and request context to determine if an action would be allowed or not
as well as provide detailed analysis of why/why not. Neph uses the data in the graph to generate simulation requests.
Specifically, it collects the following information:

- Direct identity policies (inline, attached) (skipped for service principals)
- Group identity policies (inline, attached) (for IAM users)
- Permission boundaries
- Resource policies (if applicable to target resource)
- Service and Resource control policies for the Organization (assuming org data collection is enabled)

If a simulation succeeds, a new
edge between the principal and the service of the resource is created for that action.

For example, given:

- Principal: arn:aws:iam::12345:user/user1
- Action: s3:GetObject
- Resource: arn:aws:s3:::bucket1/file1.txt

If the action is allowed, an edge like `(:IamUser{...})-[:S3_GETOBJECT{...}]->(:Service{key:"s3"})` will be written between `arn:aws:iam::12345:user/user1` and the S3 service. The relationship properties will also contain the details of the simulation and simulation results.

The principal can also be an AWS Service ID, such as `ec2.amazonaws.com` for the EC2 service. 
As a note, even if a service principal succeeds in the simulation, the outcome results in the relationship properties may indicate the opposite.
This is due to service principals not having identity policies, so the identity policy analysis component of the simulation fails.

If the simulation fails, Neph may retry the simulation one or more times depending on why the simulation failed.
If the simulation failed because of a missing context key required to 
satify a condition, Neph will re-run the simulation with that key added to the context.
For example, if a role trust policy requires an external ID and a simulation
for sts:AssumeRole fails due to that key missing, Neph will add the ID
to the request then re-run the simulation.
Neph will also re-run failed simulations for actions that support API equivalence (see https://sra.io/blog/an-overview-of-deputies-in-aws/ -> API Equivalence).

