#!/usr/bin/env python3
""" Build and deploy a python lambda

1) Read private.yaml and load each file mentioned which should have .template
   in the filename, replace any variables in the file with the appropriate
   values in private.yaml.  Write out a combined version of the file without
   the .template

   This is to easly allow for publishing 'template' versions of files/templates
   publicly.  The generated not-template files and private.yaml can be exlcuded
   from the repo.  TODO - reverse this, store everything with private values
   including the generated files with .private. in the name, that way it is
   easy to ignore them in .gitignore

Private variables go in private.yaml in the format of:
filename.template.yaml:
  PARAMETER:  value
  PARAMETER2: value
filename2.template.yaml:
  PARAMETER: value

2) Open deploy_parameters.yaml (which could have been generated from step #1)
   This file should contain the specifics for the deployment (stack, lambda
   bucket, etc.

"""

import boto3
import botocore
import yaml
import sys
import os
import subprocess
import shutil
import argparse
from distutils.util import strtobool

# Nasty global
config = ''


def yes_no_query(question):
    sys.stdout.write('{} [y/n]\n'.format(question))
    while True:
        try:
            return strtobool(input().lower())
        except ValueError:
            sys.stdout.write('Please respond with \'y\' or \'n\'.\n')


def bucket_exists_in_region(bucketname):
    s3 = boto3.client('s3')
    if config['region'] == 'us-east-1':
        location = None
    else:
        location = config['region']

    for bucket in s3.list_buckets()["Buckets"]:
        if (bucket['Name'] == bucketname and
            (s3.get_bucket_location(Bucket=bucket['Name'])
             ['LocationConstraint']) == location):
            return(True)
    return(False)


def create_bucket(bucketname):
    s3 = boto3.resource('s3', region_name=config['region'])
    '''
    Dumb issue with specifying us-east-1 region
    https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html
    '''
    if config['region'] == 'us-east-1':
        bucket = s3.create_bucket(Bucket=bucketname)
    else:
        bucket = s3.create_bucket(Bucket=bucketname,
                                  CreateBucketConfiguration={
                                      'LocationConstraint': config['region']})
    print("Created bucket {}".format(bucketname))


def main():
    # ensure using global config
    global config

    # Load and process customizations
    private = yaml.safe_load((open('private.yaml')))
    for templatefilename in private:
        templatefile = open(templatefilename, 'r')
        new = templatefile.read()
        for replacement in private[templatefilename].items():
            new = new.replace(*replacement)
        newfilename = templatefilename.replace('.template', '')
        newfile = open(newfilename, 'w')
        newfile.write(new)
        templatefile.close()
        newfile.close()
        print('{} --> {}'.format(templatefilename, newfilename))

    # Load the configuration settings
    print('Loading parameters in deploy_parameters.yaml')
    config = yaml.safe_load(open('deploy_parameters.yaml'))

    parser = argparse.ArgumentParser()
    parser.add_argument('--nobuild', action='store_true',
                        help='Skip build step', required=False)
    parser.add_argument('--nodeploy', action='store_true',
                        help='Skip deployment of lambda code', required=False)
    args = parser.parse_args()

    # Validate the cloudformation template
    cmd = ("aws cloudformation validate-template "
           f"--template-body file://{config['cloudformation_template']} "
           )
    print(cmd)
    try:
        validate_cmd = subprocess.check_call(cmd.split(" "))
    except subprocess.CalledProcessError:
        print('Cloudformaiton template validation failed')
        exit()

    # if lambda_bucket is set, ensure it exists
    if 'lambda_bucket' in config.keys():
        if not bucket_exists_in_region(config['lambda_bucket']):
            print("Error: Required s3 bucket {} does not exist in region "
                  "{}".format(config['lambda_bucket'], config['region']))
            if yes_no_query("Create {}?".format(config['lambda_bucket'])):
                create_bucket(config['lambda_bucket'])
            else:
                sys.exit("exiting")

    if not args.nobuild:
        # Run 'sam build' on the cloudformaiton template.  This
        # Will package up the lambda files
        cmd = ("sam build "
               f"--template-file {config['cloudformation_template']} "
               f"--build-dir {config['deploy_dir']} "
               f"--region {config['region']} "
               )
        print(cmd)
        package_cmd = subprocess.run(cmd.split(" "))

        # Set permissions
        for root, dirs, files in os.walk(config['deploy_dir']):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o0755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o0644)

    # Now Deploy the Stack

    if config['environment'] != 'prod':
        stackname = 'Dev' + config['stackname']
    else:
        stackname = config['stackname']
    if not args.nodeploy:
        cmd = ("sam deploy "
               "--template-file "
               f"{config['deploy_dir']}/template.yaml "
               f"--stack-name {stackname} "
               f"--s3-bucket {config['lambda_bucket']} "
               f"--s3-prefix {config['lambda_prefix']} "
               f"--region {config['region']} "
               "--capabilities CAPABILITY_IAM"
               )
        print(cmd)
        deploy_cmd = subprocess.run(cmd.split(" "))


if __name__ == "__main__":
    main()
