#!/usr/bin/env bash

CERTDIR='XXCERTDIRXX'
S3LOC='XXS3LOCXX'
BINDIR='XXBINDIRXX'

# Download latest newcerts file and compare to existing one
aws s3 cp ${S3LOC}newcerts ${CERTDIR}/newcerts.latest

# if the files are different, assume new certs across the board.
# future - be smarter and look at which certs changed and restart
# just the appropriate services.

# Exit if the files are the same
diff -b ${CERTDIR}/newcerts ${CERTDIR}/newcerts.latest && exit

# Replace the certificate store
rm -rf ${CERTDIR}.bak
[[ -d ${CERTDIR} ]] && mv ${CERTDIR} ${CERTDIR}.bak
aws s3 cp --recursive ${S3LOC} ${CERTDIR}

${BINDIR}/fixcertlinks.py ${CERTDIR}

## CUSTOMIZE BELOW AS NEEDED TO RESTART SERVICES ###
# Restart postfix
if systemctl list-units --full | grep -Fq "postfix.service"; then
  systemctl reload postfix
fi

# Restart httpd
if systemctl list-units --full | grep -Fq "php-fpm.service"; then
  systemctl reload php-fpm
fi

if systemctl list-units --full | grep -Fq "httpd.service"; then
  systemctl restart httpd
fi
