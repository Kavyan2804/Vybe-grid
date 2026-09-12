#!/bin/bash
# Fail if anything under optimizer/infrastructure references scenariogen
set -e

if grep -rn "scenariogen" optimizer/infrastructure/; then
    echo "ERROR: optimizer/infrastructure contains references to scenariogen!"
    exit 1
fi

echo "OK: No references to scenariogen found in optimizer/infrastructure."
exit 0
