#!/usr/bin/env python
import yaml
import os
import argparse
import libvirt
import logging
import imp
import csv
import numpy
import json
import signal
from jinja2 import Template
from lib.winrm_extra import winrm_port_online, run_ps

base_path = os.getcwd()
cfg_path = base_path + '/config/'
tmp_path = base_path + '/temp/'
template_path = base_path + '/templates/'

logger = logging.getLogger('setup_config')

ch = logging.StreamHandler()
fmt = logging.Formatter('%(asctime)s %(levelname)s: [setup_config] %(message)s', datefmt='%d/%m/%Y %T')
ch.setFormatter(fmt)
logger.addHandler(ch)

with open(cfg_path + 'parameters.conf') as f:
    parameters = imp.load_source('parameters', '', f)


class Timeout():
    """Timeout class using ALARM signal."""
    class Timeout(Exception):
        pass

    def __init__(self, sec):
        self.sec = sec

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.raise_timeout)
        signal.alarm(self.sec)

    def __exit__(self, *args):
        signal.alarm(0)    # disable alarm

    def raise_timeout(self, *args):
        raise Timeout.Timeout()


def read_args():

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--protocol', help='Network protocol.',
                        choices=['tcp', 'udp'], required=True)
    parser.add_argument('-i', '--iterations', help='Number of iterations of the test.',
                        type=int, choices=xrange(1, 20), required=True)
    parser.add_argument('-t', '--threads', help='Number of threads for the test.',
                        type=int, choices=xrange(1, 32), required=True)
    parser.add_argument('-d', '--driver', help='Driver configuration.',
                        required=True)
    parser.add_argument('-c', '--csv', help='Display results in CSV', action="store_true")
    parser.add_argument('-v', '--verbose', help='Show debug messages', action="store_true")
    args = parser.parse_args()

    return args


def readable(num):
    for unit in ['', 'K', 'M', 'G', 'T', 'P']:
        if num < 1000:
            return "%.2f %s%s" % (num, unit, "bits/sec")
        num /= 1000.0
    return 0


def render_config_file(template_file, config_file, driver_config, output_file):
    temp = template_path + template_file
    conf = cfg_path + config_file

    with open(temp, 'r') as f:
        template = Template(f.read())

    with open(conf, 'r') as f:
        cfg = yaml.load(f)

    # Validate parameter
    if driver_config in cfg:
        output = template.render(cfg[driver_config])

        with open(tmp_path + output_file, 'w') as f:
            f.write(output)

        applied_config = {}
        for option in cfg[driver_config]['Options']:
            applied_config[option['Name']] = option['Value']

        return applied_config

    else:
        logger.error("ERROR: Config " + driver_config + " does not exist.")
        logger.error("Please check " + conf)
        os._exit(1)


def render_test_file(template_file, parameters, args, output_file):
    temp = template_path + template_file

    with open(temp, 'r') as f:
        template = Template(f.read())

    output = template.render(server=parameters.IPERF_SERVER, protocol=args.protocol,
                             udpflags=parameters.IPERF_C_UDP, timeout=parameters.RUN_TIME,
                             guest_log_path=parameters.GUEST_LOG_DIR, threads=args.threads)

    with open(tmp_path + output_file, 'w') as f:
        f.write(output)


def warming_run(template_file, parameters, args, credentials):
    temp = template_path + template_file

    with open(temp, 'r') as f:
        template = Template(f.read())

    output = template.render(server=parameters.IPERF_SERVER, protocol=args.protocol,
                             udpflags=parameters.IPERF_C_UDP, timeout=parameters.WARMING_TIME,
                             threads=args.threads)

    with open(tmp_path + 'warming_run.ps1', 'w') as f:
        f.write(output)

    # Start iperf server
    logger.debug("- Starting iperf server for warming run")
    cmd = ' '.join(['./s_iperf.sh', str(args.threads), str(args.protocol)])
    logger.debug("Executing cmd: %s" % cmd)
    os.system(cmd)

    # Start iperf client
    logger.debug("- Starting iperf client for warming run")
    output = run_ps(tmp_path + "warming_run.ps1", parameters.IPERF_CLIENT, credentials, 1)
    logger.debug("PS Output: " + output[2])

    # Stop iperf server
    logger.debug("- Stopping iperf server")
    os.system("killall -9 iperf")


def guest_results(credentials, parameters):
    # Render template
    temp = template_path + "get_guest_results.ps1.template"
    ps1_file = tmp_path + "get_guest_results.ps1"
    with open(temp, 'r') as f:
        template = Template(f.read())

    output = template.render(guest_log_path=parameters.GUEST_LOG_DIR)
    with open(ps1_file, 'w') as f:
        f.write(output)

    # Gather results in JSON
    results = run_ps(ps1_file, parameters.IPERF_CLIENT, credentials, 1)
    return results[1]


def host_results(host_log_path):
    # TODO: convert CSV to JSON and return values
    bandwidth = 0
    transferred = 0
    stddev = []
    for file in os.listdir(host_log_path):
        if file.endswith(".csv"):
            with open(host_log_path + file, 'rb') as csvfile:
                csvreader = csv.reader(csvfile)
                for row in csvreader:
                    transferred = transferred + int(row[7])
                    logger.debug(file + " transferred :" + row[7])
                    bandwidth = bandwidth + int(row[8])
                    logger.debug(file + " bandwidth :" + row[8])
                    stddev.append(int(row[8]))

    logger.info("Total data transferred: " + readable(transferred))
    logger.info("Total bandwidth: " + readable(bandwidth))
    logger.info("Standard deviation: " + str(numpy.std(stddev)))


def setup_guest_driver(credentials, guest_ip, setup_ps1):
    # Change driver configuration
    logger.info("Configuring driver in guest")
    try:
        with Timeout(15):
            output = run_ps(setup_ps1, guest_ip, credentials, 0)
            logger.debug("PS Output: " + output[2])
    except Timeout.Timeout:
        logger.debug("Driver configuration timed out, closing connection to guest.")

    signal.alarm(0)


def validate_driver_config(credentials, guest_ip, cfg):
    logger.info("Verifying if driver configuration has been applied")
    output = run_ps(template_path + "get_driver_config.ps1", guest_ip, credentials, 1)
    data = json.loads(output[1])
    for option in data:
        if cfg[option["DisplayName"]] != option["DisplayValue"]:
            logger.error['Failure during driver configuration.']
            raise SystemExit
        logger.debug('- ' + option["DisplayName"] + ' : ' + option["DisplayValue"])


def parse_results(threads, results):
    logger.info("Parsing results")
    data = json.loads(results)
    iteration_tp = 0
    iteration_samples = []
    while threads > 0:
        logger.debug("Output from thread %s", threads)
        # logger.debug(data[str(threads) + ".csv"])
        thread_tp = 0
        thread_samples = []

        # Throughput results
        sample_count = 0
        for sample in data[str(threads) + ".csv"]:
            sample_count += 1
            # logger.debug(int(sample['Throughput']))
            thread_tp = thread_tp + int(sample['Throughput'])
            thread_samples.append(int(sample['Throughput']))

        thread_tp = thread_tp / sample_count
        thread_stddev = numpy.std(thread_samples)

        iteration_tp = iteration_tp + thread_tp
        logger.info("- Thread %s average throughput: %s", threads, readable(thread_tp))
        logger.info("- Thread %s std dev: %s (%.2f%%)", threads, readable(thread_stddev), (100 * thread_stddev / thread_tp))

        iteration_samples.append(thread_tp)
        threads -= 1
        iteration_stddev = numpy.std(iteration_samples)

    logger.info("Average throughput for this iteration: %s", readable(iteration_tp))
    logger.info("Std dev for this iteration: %s (%.2f%%)", readable(iteration_stddev), (100 * iteration_stddev / iteration_tp))

    return iteration_tp


def print_csv(driver, iteration, threads, results):
    data = json.loads(results)

    csv_row = ['Driver config', 'Iteration', 'Thread', 'Run time', 'Throughput']
    thread = 1
    while thread <= threads:
        for sample in data[str(threads) + ".csv"]:
            csv_values = [driver, iteration, threads, sample['Run_Time'], int(sample['Throughput'])]
            csv_row = ','.join(str(value) for value in csv_values)
            print(csv_row)
        thread += 1


def main():
    logger.setLevel(logging.INFO)
    args = read_args()

    if args.verbose is True:
        logger.setLevel(logging.DEBUG)

    # Hide everything but errors
    # csv ignores verbosity parameter
    if args.csv is True:
        logger.setLevel(logging.ERROR)

    # Define VM from template
    lv = libvirt.open('qemu:///system')
    try:
        vm = lv.lookupByName(parameters.VM_NAME)
        if vm.isActive() is False:
            logger.info(parameters.VM_NAME + " is not running. Starting")
            vm.start()

    except libvirt.libvirtError:
        logger.info("VM " + parameters.VM_NAME + " doesn't exist.")

    # Set WinRM credentials
    credentials = (parameters.USERNAME, parameters.PASSWORD)

    # Render PS1 file for driver config
    logger.debug("Rendering driver config PS1")
    driver_config = render_config_file("set_driver_config.ps1.template", "driver_definitions.yml",
                                       args.driver, "set_driver_config.ps1")

    # Render PS1 file for client run
    logger.debug("Rendering client run PS1")
    render_test_file("client_iperf.ps1.template", parameters, args, "client_iperf.ps1")

    # Wait until the VM finishes booting
    winrm_port_online(parameters.IPERF_CLIENT, parameters.VM_NAME)

    # Change driver configuration
    setup_guest_driver(credentials, parameters.IPERF_CLIENT, tmp_path + "set_driver_config.ps1")

    # Verify that the configuration has been applied
    validate_driver_config(credentials, parameters.IPERF_CLIENT, driver_config)

    # Remove old log files
    host_log_path = parameters.HOST_LOG_DIR + '/'
    cmd = ' '.join(['rm', host_log_path + 'server*.csv'])
    os.system(cmd)

    # Warming up run
    logger.info("Warm up run")
    warming_run("warming_run.ps1.template", parameters, args, credentials)

    iteration = 1
    throughput = []
    while iteration <= args.iterations:
        logger.info("Running iteration " + str(iteration))
        iteration += 1

        # Start iperf server
        logger.info("- Starting iperf server")
        cmd = ' '.join(['./s_iperf.sh', str(args.threads), str(args.protocol)])
        logger.debug("Executing cmd: %s" % cmd)
        os.system(cmd)

        # Start iperf client
        logger.info("- Starting iperf client")
        output = run_ps(tmp_path + "client_iperf.ps1", parameters.IPERF_CLIENT, credentials, 1)
        logger.debug("PS Output: " + output[2])

        # Gather guest results
        logger.debug("Gathering test results from guest")
        gresults = guest_results(credentials, parameters)
        logger.debug(gresults)

        # Gather host results
        # host_results(host_log_path)

        # Stop iperf server
        logger.info("- Stopping iperf server")
        os.system("killall -9 iperf")

        if args.csv is True:
            # Show CSV from guest results
            print_csv(args.driver, iteration - 1, args.threads, gresults)

        else:
            # Show human readable results
            iteration_tp = parse_results(args.threads, gresults)
            throughput.append(iteration_tp)

    if args.csv is not True:
        run_tp = sum(throughput) / args.iterations
        run_std = numpy.std(throughput)
        logger.info("Run average throughput: " + readable(run_tp))
        logger.info("Std dev for this run: %s (%.2f%%)", readable(run_std), (100 * run_std / run_tp))


if __name__ == '__main__':

    main()
