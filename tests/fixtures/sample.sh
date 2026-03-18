#!/usr/bin/env bash
# Deploy helper — builds and deploys the Firebase functions.

export FIREBASE_PROJECT="side-eye-2163b"
export DEPLOY_ENV="production"

deploy_functions() {
    firebase deploy --only functions
}

run_tests() {
    flutter test
}

cleanup() {
    rm -rf build/
}
