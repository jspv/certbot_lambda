# certbot_lambda

cerbot_lambda is an aws lambda that will periodically check to see if the
specified letsencrypt certificates are due for renewal and if so, will renew
the and upload them to a designated s3 bucket.

certbot_lambda uses a CloudWatch timer as a trigger (default: daily), it will
pull the existing certificates from the designated s3 bucket, and will use
the certbot module to check for renewal using the route53 authentication method.  Upon each renewal it will update
a file ```newcerts``` which can be monitored by an ec2 for changes and take the
appropriate action.

## Installation

certbot_lamda comes with a quick lambda deployment script ``deploy.py`` that will

1. create a customized CloudFormation template with your speicific settings
1. package up the lambda function with all it's necessary dependencies using ```aws sam```
1. deploy the stack including the lambda and related CloudWatch timer to your aws
account

### Customize the lambda by editing private.yaml

Copy the ```private.yaml.example``` to ```private.yaml``` and review and edit the parameters to match your AWS setup.  ```deploy.py``` uses private.yaml to replace placeholders in both the ```deploy_parameters.template.yaml``` and ```certbot_cf.template.yaml``` files with your local customizations.  A few notes:
* putting ```dev``` in the ```deploy_parameters.template.yaml``` section for ```MY_ENV``` will cause dev- to be prepended to certificate bucket prefix so you don't actually overwrite production certs when testing.
* putting ```dev``` in the ```certbot_cf.template.yaml``` section for ``` MYENV``` will cause the lambda to use the letsencrypt stage servers to issue test certificates.  This is important while testing to not hit the letsencrypt production certificate issues for your domains.
* the bucket listed in ```MY_LAMBDA_BUCKET``` will be created if it doesn't already exist
* ```MYSENTRYDSN``` is for using [sentry.io](); it's free and helpful, so if you don't have it, take a look.  If you don't want to use it it can be removed from the lambda pretty obviously.
* for ```MYDOMAINLIST``` use a ```/``` character to separate each certificate, use a ```,``` to separate each domain to be added to the certificate.  For example the following will generate two certificates:

    1. first certificate with foo.com and bar.com listed
    1. second certificate with foobar.com listed

    ```MYDOMAINLIST: foo.com,bar.com/foobar.com```


* Add ```MYZONEX``` entries incrementing X for each Route53 domain. The cloudformation template is execting four of them (I have four domains), so if you're using a different number, add/remove the appropriate matching lines in ```certbot_cf.template.yaml```

### Usage

```pipenv run ./deploy.py``` will create the templates, run ```sam build``` and ```sam deploy``` to install the lambda.  

```pipenv run ./deploy.py``` can take a few arguments:
* ```--nobuild```: Skip build step.  Good if you're just tweaking the deploy parameters

* ```--nodeploy```: Skip deployment of lambda code'.  Good while debugging and testing with the lambda locally

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
[MIT](https://choosealicense.com/licenses/mit/)
