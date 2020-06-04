#!/usr/bin/env python3

import sys
import os
import glob
import re


def noendslash(x):
    ''' remove a slash at the end for non-empty strings '''
    return x if not x else x[:-1] if x[-1] == '/' else x


def find_latest_pem_file(dir, namebase):
    """ from a list of files with the namebase, find the latest version """

    def extract_number(file):
        """ Extracts the number at the end of the filename """
        s = re.findall(r"(\d+).pem$", file)
        return (int(s[0]) if s else -1, file)

    files = glob.glob(dir + '/' + namebase + '*.pem')
    return(max(files, key=extract_number))

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


def localize_conffile(confdir):
    confdir = noendslash(confdir)
    files = glob.glob(confdir + '/renewal/*.conf')
    for filename in files:
        with open(filename) as f:
            newText = f.read().replace('/tmp/certbot/config', confdir)
        with open(filename, "w") as f:
            f.write(newText)


if __name__ == "__main__":
    update_symlinks(sys.argv[1])
    localize_conffile(sys.argv[1])
