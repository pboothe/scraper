FROM google/cloud-sdk
MAINTAINER Peter Boothe <pboothe@google.com>
# Install all the standard packages we need
RUN apt-get update && apt-get install -y python-pip rsync tar
# Install all the python requirements
ADD requirements.txt /requirements.txt
RUN pip install -r requirements.txt
# Install scraper
ADD scraper.py /scraper.py
RUN chmod +x /scraper.py
ADD run_scraper.py /run_scraper.py
RUN chmod +x run_scraper.py
## Set up health checking
# ADD check-health.sh /check-health.sh
# RUN chmod +x check-health.sh
# HEALTHCHECK CMD ./check-health.sh || exit 1
# All daemons must be started here, along with the job they support.
CMD /run_scraper.py --rsync_host=$RSYNC_HOST --rsync_module=$RSYNC_MODULE --data_dir=scraper_data --spreadsheet=143pU25GJidW2KZ_93hgzHdqTqq22wgdxR_3tt3dvrJY
