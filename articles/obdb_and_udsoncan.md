# Combining OBDb and Udsoncan to query car data

## Introduction

The OBDb database (https://github.com/OBDb/) contains a lot of schemas to 
interpret UDS data for a wide variety of cars and Udsoncan 
(https://udsoncan.readthedocs.io/en/latest/index.html) provides an industrial strenght python module for communicating with a cars UDS interface.  However, 
it can be a challenge to get all the bits together to get the communication 
flowing and interpreting the data correctly.

## Source code examples

The python scripts in [../sources/obdbudsoncan/](../sources/obdbudsoncan/) has some complete examples on how to use Udsoncan for the communication and OBDb for interpreting the results.
