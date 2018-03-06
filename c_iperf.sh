#!/bin/bash

. ./lib/common.sh
. ./config/parameters.conf

validate_params $@

NOF_IPERF_INSTANCES=$1

if [[ $2 == "udp" ]]; then
  IPERF_EXTRA=${IPERF_C_UDP}
elif [[ $2 == "tcp" ]]; then
  IPERF_EXTRA=${IPERF_C_TCP}
else
  echo ${USAGE}
  exit 1
fi


killall iperf 2>/dev/null

echo -e "Running ${NOF_IPERF_INSTANCES} iperf $2 instances\n"

for i in $(seq 1 $NOF_IPERF_INSTANCES) ; do
  PORT=$(expr $PORT_BASE + $i)
  touch ${LOG_DIR}/client_${PORT}.csv
  ${IPERF} -c ${IPERF_SERVER} -t ${RUN_TIME} -p ${PORT} -y c \
	  ${IPERF_EXTRA} >>${LOG_DIR}/client_${PORT}.csv 2>&1 &
done
