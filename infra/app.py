import aws_cdk as cdk

from stacks.acutal_stack import AcutalStack

app = cdk.App()
AcutalStack(app, "AcutalStack", env=cdk.Environment(
    account=None,  # Uses default AWS account
    region="us-east-1",
))
app.synth()
