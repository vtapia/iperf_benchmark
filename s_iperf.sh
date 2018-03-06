#!/bin/bash

. ./config/parameters.conf
. ./lib/common.sh

validate_params $@

NOF_IPERF_INSTANCES=$1

if [[ $2 == "udp" ]]; then
  IPERF_EXTRA=${IPERF_S_UDP}
elif [[ $2 == "tcp" ]]; then
  IPERF_EXTRA=${IPERF_S_TCP}
else
  echo "ERROR: Must define tcp or udp to run the test."
  echo ${USAGE}
  exit 1
fi


killall iperf 2>/dev/null

for i in $(seq 1 ${NOF_IPERF_INSTANCES}) ; do
	PORT=$(expr ${PORT_BASE} + $i)
	touch ${HOST_LOG_DIR}/server_${PORT}.csv
	${IPERF} -s -p ${PORT} -y c \
	  ${IPERF_EXTRA} >> ${HOST_LOG_DIR}/server_${PORT}.csv 2>&1 &
done
