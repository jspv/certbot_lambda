"""
Started from:
https://gist.github.com/arkadiyt/5d764c32baa43fc486ca16cb8488169a
https://medium.com/swlh/free-ssl-certificates-with-certbot-in-aws-lambda-991eb24ac1f3
https://github.com/vittorio-nardone/certbot-lambda

Expects the following environment variables:

LETSENCRYPT_DOMAINS
LETSENCRYPT_EMAIL
NOTIFICATION_SNS_ARN
SENTRY_DSN

"""

import boto3
import certbot.main
import datetime
import os
import sentry_sdk
import subprocess
import argparse
import re
import glob
import datetime
import shutil
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

# Initialze Sentry
sentry_sdk.init(integrations=[AwsLambdaIntegration()])

# Gobals
CONFIGDIR = '/tmp/certbot/config/'
WORKDIR = '/tmp/certbot/work/'
LOGDIR = '/tmp/certbot/logs/'
NEWCERTFILE = CONFIGDIR + 'newcerts'


def endslash(x):
    ''' ensure slash at the end for non-empty strings '''
    return x if not x else x + "/" if x[-1] != '/' else x


def noendslash(x):
    ''' remove a slash at the end for non-empty strings '''
    return x if not x else x[:-1] if x[-1] == '/' else x


def nostartslash(x):
    ''' remove a slash at the beginning of a string '''
    return x if not x else x[1:] if x[0] == '/' else x


def noslashes(x):
    ''' trim single beginning and end slashes for non empty strings '''
    return nostartslash(noendslash(x))


def find_latest_pem_file(dir, namebase):
    """ from a list of files with the namebase, find the latest version """

    def extract_number(file):
        """ Extracts the number at the end of the filename """
        s = re.findall(r"(\d+).pem$", file)
        return (int(s[0]) if s else -1, file)

    files = glob.glob(dir + '/' + namebase + '*.pem')
    return(max(files, key=extract_number))


def get_last_certitme():
    ''' get the last timestamp from the NEWCERTFILE '''
    try:
        with open(NEWCERTFILE, "r") as file:
            for last_line in file:
                pass
    except FileNotFoundError:
        return 0
    last_cert_time = int(last_line.split(' ', 1)[0])
    return last_cert_time


# Add back the symlinks after pulling from s3
def update_symlinks(confdir):
    ''' his method recreates symlinks removing downloaded regular files '''
    # ensure no slash at the end of confdir
    confdir = noendslash(confdir)
    # Get list of certficate folders
    folders = glob.glob(confdir + '/archive/*/')
    for folder in folders:
        base = os.path.basename(os.path.normpath(folder))
        for k in ['cert', 'chain', 'privkey', 'fullchain']:
            try:
                print('removing {}'.format(confdir +
                                           '/live/{}/{}.pem'.format(base, k)))
                os.remove(confdir + '/live/{}/{}.pem'.format(base, k))
            except Exception as e:
                pass
            os.symlink(
                find_latest_pem_file(
                    confdir + '/archive/{}/'.format(base), k),
                confdir + '/live/{}/{}.pem'.format(base, k))


def upload_files(localpath, prefix, bucketname):
    ''' upload files to s3, removing first three parts of localpath
        e.g. /tmp/certbot/configdir '''
    session = boto3.Session()
    s3 = session.resource('s3')
    bucket = s3.Bucket(bucketname)

    for subdir, dirs, files in os.walk(localpath):
        for file in files:
            full_path = os.path.join(subdir, file)
            key = (prefix +
                   full_path[len(localpath):])
            with open(full_path, 'rb') as data:
                print("Uploading Key {}".format(key))
                bucket.put_object(Key=key, Body=data)


def download_files(path, prefix, bucketname):
    ''' download files from s3 '''

    def download_dir(prefix, localpath, bucketname, client):
        """
        params:
        - prefix: pattern to match in s3
        - localpath: local path to folder in which to place files
        - bucket: s3 bucket with target contents
        - client: initialized s3 client object

        credit https://stackoverflow.com/questions/31918960/boto3-to-download-all-files-from-a-s3-bucket/31929277s
        """  # noqa
        keys = []
        dirs = []
        next_token = ''
        base_kwargs = {
            'Bucket': bucketname,
            'Prefix': prefix,
        }
        while next_token is not None:
            kwargs = base_kwargs.copy()
            if next_token != '':
                kwargs.update({'ContinuationToken': next_token})
            results = client.list_objects_v2(**kwargs)
            contents = results.get('Contents')
            # Return if no objects to download
            if not contents:
                return
            for i in contents:
                k = i.get('Key')
                if k[-1] != '/':
                    keys.append(k)
                else:
                    dirs.append(k)
            next_token = results.get('NextContinuationToken')
        for d in dirs:
            dest_pathname = os.path.join(localpath, d[len(prefix):])
            print(f'Downloading DIR {dest_pathname}')
            if not os.path.exists(os.path.dirname(dest_pathname)):
                os.makedirs(os.path.dirname(dest_pathname))
        for k in keys:
            dest_pathname = os.path.join(localpath, k[len(prefix):])
            print(f'Downloading FILE {dest_pathname}')
            if not os.path.exists(os.path.dirname(dest_pathname)):
                os.makedirs(os.path.dirname(dest_pathname))
            client.download_file(bucketname, k, dest_pathname)

    # Make sure we're starting clean
    shutil.rmtree(path, ignore_errors=True)
    session = boto3.Session()
    s3 = session.client('s3')

    download_dir(prefix, path, bucketname, client=s3)
    update_symlinks(path)


def provision_cert(email, domains):

    # Log any rernewed cert to a single file with timestamps.  This file can
    # be monitored downstream to detect new certs
    deployhook_cmd = (
        "echo \"" + str(int(datetime.datetime.now().timestamp())) + " " +
        datetime.datetime.utcnow().replace(microsecond=0).isoformat() +
        " - $RENEWED_LINEAGE $RENEWED_DOMAINS\" >> " + NEWCERTFILE)

    certbot_args = [
        'certonly',                     # Obtain or renew a cert
        '-n',                           # Run in non-interactive mode
        '--agree-tos',                  # Agree to the terms of service,
        '--email', email,               # Email
        '--dns-route53',                # Use dns challenge with route53
        '-d', domains,                  # Domains to provision certs for
        # '-v',                           # verbosity
        # Override directory paths so script doesn't have to be run as root
        '--config-dir', CONFIGDIR,
        '--work-dir', WORKDIR,
        '--logs-dir', LOGDIR,
        '--deploy-hook', deployhook_cmd
    ]

    # Stage or Prod?
    if os.environ['CERTBOT_ENV'] != 'prod':
        certbot_args.extend(['--test-cert'])

    # Force Renew?
    if os.environ['LETSENCRYPT_FORCE_RENEW'] == "true":
        certbot_args.extend(['--force-renewal'])

    print('Calling certbot for domains: {}'.format(domains))
    certbot.main.main(certbot_args)


def handler(event, context):
    print('Made it to the handler')

    # make sure we don't overwrite prod certs when testing and
    # make sure we have a slash at the end.
    if os.environ['CERTBOT_ENV'] != 'prod':
        s3prefix = 'dev-' + \
            endslash(os.environ['LETSENCRYPT_CERTBUCKET_PREFIX'])
    else:
        s3prefix = (
            endslash(os.environ['LETSENCRYPT_CERTBUCKET_PREFIX']))
    download_files(CONFIGDIR, s3prefix, os.environ['LETSENCRYPT_CERTBUCKET'])
    initial_cert_time = get_last_certitme()

    # Certs are separated by '/', domains in a cert by ','
    for domains in os.environ['LETSENCRYPT_DOMAINS'].split('/'):
        try:
            cert = provision_cert(os.environ['LETSENCRYPT_EMAIL'], domains)
        except Exception as e:
            with sentry_sdk.push_scope() as scope:
                sentry_sdk.capture_exception(e)
            raise

    if get_last_certitme() > initial_cert_time:
        upload_files(CONFIGDIR, s3prefix, os.environ['LETSENCRYPT_CERTBUCKET'])


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--domains', help='domains to get certs for', required=True)
    parser.add_argument(
        '--email', help='email to register with', required=True)
    parser.add_argument(
        '--prod', help='Use production servers', required=False)
    parser.add_argument(
        '--bucket', help='Bucket to store certs', required=True)
    parser.add_argument(
        '--prefix', help='Bucket Prefix', required=False)
    parser.add_argument(
        '-f', '--force', action='store_true',
        help='Force Renew',
        required=False)
    args = parser.parse_args()
    os.environ['LETSENCRYPT_DOMAINS'] = args.domains
    os.environ['LETSENCRYPT_EMAIL'] = args.email
    os.environ['LETSENCRYPT_CERTBUCKET'] = args.bucket
    if args.prefix:
        os.environ['LETSENCRYPT_CERTBUCKET_PREFIX'] = args.prefix
    else:
        os.environ['LETSENCRYPT_CERTBUCKET_PREFIX'] = ""
    if args.force:
        os.environ['LETSENCRYPT_FORCE_RENEW'] = "True"
    else:
        os.environ['LETSENCRYPT_FORCE_RENEW'] = "False"
    if args.prod:
        os.environ['CERTBOT_ENV'] = 'prod'
    else:
        os.environ['CERTBOT_ENV'] = 'dev'

    event = {}

    handler(event, "foo")
