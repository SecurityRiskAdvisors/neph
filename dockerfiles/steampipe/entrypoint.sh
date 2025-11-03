#!/bin/bash
if [[ -z "${STEAMPIPE_PASSWORD}" ]]; then
    dbpassword="password"
else
    dbpassword="${STEAMPIPE_PASSWORD}"
fi
echo "$dbpassword" > /home/steampipe/.steampipe/internal/.passwd
exec steampipe service start --foreground --show-password
