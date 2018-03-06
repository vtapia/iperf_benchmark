USAGE="USAGE: $0 Number_of_concurrent_iperfs Protocol"

function validate_params {
  if [[ $# -ne 2 ]]; then
    echo "ERROR: Incorrect number of parameters ($#)"
    echo ${USAGE}
    exit 1
  fi

  if [[ $1 =~ ^-?[0-9]+$ ]]; then
    :
  else
    echo "ERROR: first parameter must be an integer."
    echo ${USAGE}
    exit 1
  fi
}

