FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true
RUN apt update && \
    apt install -y curl

# https://steampipe.io/downloads?install=linux
RUN /bin/sh -c "$(curl -fsSL https://steampipe.io/install/steampipe.sh)"

# cannot run steampipe as root
RUN useradd -ms /bin/bash -d /home/steampipe steampipe
USER steampipe

RUN mkdir -p /home/steampipe/.steampipe/config
COPY steampipe/workspace.spc.example /home/steampipe/.steampipe/config/workspace.spc
RUN steampipe plugin install aws

COPY steampipe/entrypoint.sh /home/steampipe/entrypoint.sh
CMD ["/home/steampipe/entrypoint.sh"]
