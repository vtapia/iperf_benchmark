#!/bin/bash

SUM_MARKER_MBPS="Mbits\/sec"
SUM_MARKER_GBPS="Gbits\/sec"

get_val() {
STR=$1
VALNO=$2
DELIMITER=$3
        echo "${STR}" | awk -F"$DELIMITER" "{print \$$VALNO}"
}


parse_file_mbps() {
FNAME=$1
MARKER=$2
if [ -z $FNAME ]; then
	echo "ERROR: file name has to be defined"
	return 1
fi

if [ x"$MARKER" = x"$SUM_MARKER_MBPS" ]; then
	FACTOR=1
elif [ x"$MARKER" = x"$SUM_MARKER_GBPS" ]; then
	FACTOR=1024
else
	echo "ERROR: Invalid marker: $MARKER"
	return 1
fi


SUM=0
while read -r line ; do
	v=$(get_val "$line" 6 " ")
	SUM=$(echo "$SUM" "$v" "$FACTOR" | awk '{print $1  + $2 * $3}')
done <<EOT
$(grep "$MARKER" $FNAME)
EOT

echo $SUM
return 0
}

parse_file() {
FNAME=$1
if [ -z $FNAME ]; then
	echo "ERROR: file name has to be defined"
	return 1
fi
	VMBPS=$(parse_file_mbps "$FNAME" $SUM_MARKER_MBPS)
	if [ $? -ne 0 ]; then
		echo "ERROR: cannot get MBPS SUM for $IFNAME"
		return 1
	fi

	VGBPS=$(parse_file_mbps "$FNAME" $SUM_MARKER_GBPS)
        if [ $? -ne 0 ]; then
		echo "ERROR: cannot get GBPS SUM for $IFNAME"
		return 1
	fi


	SUM=$(echo "$VMBPS" "$VGBPS" | awk '{print $1  + $2}')

	echo "  FNAME=$FNAME SUM=$SUM Mbps"
	return 0
}


RES_DIR=$1
if [ -z "$RES_DIR" ]; then
	echo "ERROR: result dir has to be defined"
	exit 1
fi

if [ ! -d "$RES_DIR" ]; then
	echo "ERROR: $RES_DIR is not a folder"
	exit 1
fi

echo "Processing folder $RES_DIR..."
for f in $RES_DIR/*
do
	parse_file "$f"
done
echo "Done"

