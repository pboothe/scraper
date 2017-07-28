#!/bin/bash

# A one-shot script that verifies that the data contained in the gs://mlab
# bucket is a subset of the data contained in the gs://archive-mlab-oti for the
# ${EXPERIMENT}/2017/06/ directory in each bucket.
#
# If this script exits successfully and never prints out FILES MISSING or FILES
# DIFFER, then we will know that the data from scraper for the month of June is
# a superset of the data from the legacy pipeline.

set -e

# The script takes a single command-line argument, namely the experiment to
# verify.
EXPERIMENT=${1:-ndt}

# Compare old and new, and if the new file has a .gz filename, use one with the
# .gz suffix instead of the passed-in name.
gzdiff ()
{
  olddir=$1
  newdir=$2
  filename=$3
  experiment=$4
  oldfile=${olddir}/${filename}
  if [[ -e ${oldfile}.gz ]]
  then
    oldfile=${oldfile}.gz
  fi
  newfile=${newdir}/${filename}
  if [[ -e ${newfile}.gz ]]
  then
    newfile=${newfile}.gz
  fi
  if [[ -f ${oldfile} && -f ${newfile} ]]
  then
    if [[ ${experiment} == "sidestream" ]]
    then
      lines=$(comm -2 -3 <(sort ${oldfile})  <(sort ${newfile}) | wc -l)
      if [[ $lines != 0 ]]
      then
        echo FILES DIFFER: ${filename}
      fi
    else
      if ! zdiff -q ${oldfile} ${newfile}
      then
        echo FILES DIFFER: ${filename}
      fi
    fi
  fi
}

for day in $(seq -w 1 30)
do
  echo $day
  slivers=$(gsutil ls gs://m-lab/${EXPERIMENT}/2017/06/${day} | sed -e 's/^.*Z-//' -e 's/-[0-9]*.tgz//' |  sort -u)
  for sliver in $(echo $slivers)
  do
    old=$(mktemp -d ./olddata.tmp.XXXXXX)
    new=$(mktemp -d ./newdata.tmp.XXXXXX)
    pushd $old
      gsutil -m cp gs://m-lab/${EXPERIMENT}/2017/06/${day}/*${sliver}*.tgz .
      for tgz in *.tgz
      do
        tar xfz ${tgz}
        rm ${tgz}
        find . | sort > filelist.txt
      done
    popd
    pushd $new
      gsutil -m cp gs://archive-mlab-oti/${EXPERIMENT}/2017/06/${day}/*${sliver}*.tgz . \
        || gsutil -m cp gs://scraper-mlab-oti/${EXPERIMENT}/2017/06/${day}/*${sliver}*.tgz .
      for tgz in *.tgz
      do
        tar xfz ${tgz}
        rm ${tgz}
        find . | sort > filelist.txt
      done
    popd
    # Only print out files that are in the legacy but not the new one.  These
    # are the missing files, and hopefully the output will have zero lines.
    missing=$(comm -2 -3 ${old}/filelist.txt <(cat ${new}/filelist.txt | sed -e 's/.gz$//' | sort -u) | wc -l)
    if [[ ${missing} == 0 ]]
    then
      echo ALL FILES ACCOUNTED FOR $day $sliver
    else
      echo FILES MISSING FOR $day $sliver
      comm -2 -3 ${old}/filelist.txt <(cat ${new}/filelist.txt | sed -e 's/.gz$//' | sort -u)
    fi
    # Print out files that are in both dirs (neglecting the .gz suffix) and
    # then gzdiff them.
    comm -1 -2 ${old}/filelist.txt <(cat ${new}/filelist.txt | sed -e 's/.gz$//' | sort -u) \
      | grep -v filelist.txt | while read; do gzdiff $old $new ${REPLY} ${EXPERIMENT}; done
    echo checked that all files have the same contents for $day $sliver
    rm -Rf ${old} ${new}
  done
  echo done with one day $day
done
