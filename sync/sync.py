#!/usr/bin/python
# Copyright 2017 Scraper Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This program uploads the status in cloud datastore to a spreadsheet.

Nodes in the MLab fleet use a spreadsheet to determine what data is and is not
safe to delete. Unfortunately, if every scraper just wrote to that spreadsheet,
then we would quickly run out of spreadsheet API quota.  Also, the spreadsheet
is kind of a janky hack for what really should be a key-value store. The new
scraper has its source of truth in a key-value store (Google Cloud Datastore),
and this program has the job of updating the spreadsheet with that truth.  In a
longer term migration, this script and the spreadsheet should both be
eliminated, and the scripts in charge of data deletion should read from cloud
datastore directly.

This program needs to be run on a GCE instance that has access to the Sheets
API  Sheets API access is not enabled by default for GCE, and it can't be
enabled from the web-based GCE instance creation interface.  Worse, the scopes
that a GCE instance has can't be changed after creation. To create a new GCE
instance named scraper-dev that has access to both cloud APIs and spreadsheet
apis, you could use the following command line:
   gcloud compute instances create scraper-dev \
       --scopes cloud-platform,https://www.googleapis.com/auth/spreadsheets
"""

import argparse
import BaseHTTPServer
import logging
import random
import SocketServer
import sys
import textwrap
import thread
import time

# pylint: disable=no-name-in-module, import-error
# google.cloud seems to confuse pylint
from google.cloud import datastore
# pylint: enable=no-name-in-module, import-error

import prometheus_client


def parse_args(argv):
    """Parses the command-line arguments.

    Args:
        argv: the list of arguments, minus the name of the binary

    Returns:
        A dictionary-like object containing the results of the parse.
    """
    parser = argparse.ArgumentParser(
        description='Repeatedly upload the synchronization data in Cloud '
                    'Datastore up to the specified spreadsheet.')
    parser.add_argument(
        '--expected_upload_interval',
        metavar='SECONDS',
        type=float,
        default=300,
        help='The number of seconds to wait between uploads (on average).  We '
             'add jitter to this number to prevent the buildup of patterns, '
             'but this specifies the average of the wait times.')
    parser.add_argument(
        '--spreadsheet',
        metavar='SPREADSHEET_ID',
        type=str,
        required=True,
        help='The ID of the spreadsheet to update')
    parser.add_argument(
        '--datastore_namespace',
        metavar='NAMESPACE',
        type=str,
        default='scraper',
        help='The cloud datastore namespace to use in the current project.')
    parser.add_argument(
        '--prometheus_port',
        metavar='PORT',
        type=int,
        default=9090,
        help='The port on which metrics are exported.')
    parser.add_argument(
        '--webserver_port',
        metavar='PORT',
        type=int,
        default=80,
        help='The port on which a summary of the sheet is exported.')
    return parser.parse_args(argv)


KEYS = ['dropboxrsyncaddress', 'contact', 'lastsuccessfulcollection',
        'errorsincelastsuccessful', 'lastcollectionattempt',
        'maxrawfilemtimearchived']


def get_fleet_data(namespace):
    """Returns a list of dictionaries, one for every entry in the namespace."""
    datastore_client = datastore.Client(namespace=namespace)
    answers = []
    for item in datastore_client.query(kind='rsync_url').fetch():
        answer = {}
        answer[KEYS[0]] = item.key.name
        for k in KEYS[1:]:
            answer[k] = item.get(k, '')
        answers.append(answer)
    return answers


class WebHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Print the ground truth from cloud datastore."""
    namespace = 'test'

    # The name is inherited, so we have to use it even if pylint hates it.
    # pylint: disable=invalid-name
    def do_GET(self):
        """Print out the ground truth from cloud datastore as a webpage."""
        logging.info('New request!')
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        print >> self.wfile, textwrap.dedent('''\
        <html>
        <head>
          <title>MLab Scraper Status</title>
          <style>
            table {
              border-collapse: collapse;
              margin-left: auto;
              margin-right: auto;
            }
            tr:nth-child(even) {
              background-color: #FFF;
            }
            tr:nth-child(even) {
              background-color: #EEE;
            }
          </style>
        </head>
        <body>
          <table><tr>''')
        data = get_fleet_data(WebHandler.namespace)
        if not data:
            print >> self.wfile, '</table><p>NO DATA</p>'
            return
        else:
            for key in KEYS:
                print >> self.wfile, '     <th>%s</th>' % key
            print >> self.wfile, '  </tr>'
            rows = sorted([d.get(key, '') for key in KEYS] for d in data)
            for data in rows:
                print >> self.wfile, '  <tr>'
                for item in data:
                    print >> self.wfile, '     <td>%s</td>' % item
                print >> self.wfile, '    </tr>'
            print >> self.wfile, '    </table>'
        print >> self.wfile, '  <center><small>', time.ctime()
        print >> self.wfile, '    </small></center>'
        print >> self.wfile, '</body></html>'
    # pylint: enable=invalid-name


def start_webserver_in_new_thread(port):  # pragma: no cover
    """Starts the wbeserver to serve the ground truth page.

    Code cribbed from prometheus_client.
    """
    server_address = ('', port)

    class ThreadingSimpleServer(SocketServer.ThreadingMixIn,
                                BaseHTTPServer.HTTPServer):
        """Use the threading mix-in to avoid forking or blocking."""

    httpd = ThreadingSimpleServer(server_address, WebHandler)
    thread.start_new_thread(httpd.serve_forever, ())


def main(argv):  # pragma: no cover
    """Update the spreadsheet in a loop.

    Set up the logging, parse the command line, set up monitoring, set up the
    datastore client, set up the spreadsheet client, set up the webserver, and
    then repeatedly update the spreadsheet and sleep.
    """
    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s %(levelname)s %(filename)s:%(lineno)d] '
               '%(message)s')
    # Parse the commandline
    args = parse_args(argv[1:])
    WebHandler.namespace = args.datastore_namespace
    # Set up spreadsheet client

    # Set up the monitoring
    prometheus_client.start_http_server(args.prometheus_port)
    start_webserver_in_new_thread(args.webserver_port)
    # Repeatedly copy information from the datastore to the spreadsheet
    while True:
        # Download
        data = get_fleet_data(args.datastore_namespace)
        # Upload

        # Sleep
        sleep_time = random.expovariate(1.0 / args.expected_upload_interval)
        logging.info('Sleeping for %g seconds', sleep_time)
        time.sleep(sleep_time)

if __name__ == '__main__':  # pragma: no cover
    main(sys.argv)
