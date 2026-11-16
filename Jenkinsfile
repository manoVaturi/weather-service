// WeatherApp CI pipeline (declarative).
// main: test, build, scan, push to ECR, bump the dev tag in the gitops repo.
// Tag vX.Y.Z: retag the image main built and open a merge request for prod.
// Argo CD deploys from the gitops repo, not from here.
// gitlab-gitops-bot is the credential that writes to the gitops repo.
// Source of truth: GitLab. A webhook with a shared secret triggers this pipeline.

def AWS_REGION = 'eu-west-1'
def ECR_REGISTRY = '<AWS_ACCOUNT_ID>.dkr.ecr.eu-west-1.amazonaws.com'
def IMAGE_REPO = 'weatherapp'

// Slack must never be able to fail a build, so every call is wrapped.
def notify(String color, String text) {
    try {
        slackSend(channel: '#devops', color: color, tokenCredentialId: 'slack-token',
                  message: "${text}\n${env.JOB_NAME} #${env.BUILD_NUMBER} (<${env.BUILD_URL}|open>)")
    } catch (err) {
        echo "Slack notification skipped: ${err.message}"
    }
}

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        booleanParam(name: 'RUN_AI_REVIEW', defaultValue: false, description: 'Run the AI review stage (week 2)')
    }

    stages {
        stage('Prepare') {
            steps {
                // Done in a stage: GIT_COMMIT does not exist yet in environment {}
                script {
                    // The git SHA is the image tag: immutable, traceable, never "latest".
                    env.IMAGE_TAG = env.GIT_COMMIT.take(7)
                    env.IMAGE = "${ECR_REGISTRY}/${IMAGE_REPO}:${env.IMAGE_TAG}"
                    // Tags that are not vMAJOR.MINOR.PATCH fail here, or Release is skipped silently
                    if (env.TAG_NAME) {
                        if (!(env.TAG_NAME ==~ /v\d+\.\d+\.\d+/)) {
                            error("Release tags look like v1.2.3, not '${env.TAG_NAME}'. Delete the tag and push a correct one.")
                        }
                        env.VERSION = env.TAG_NAME.substring(1)
                    }
                }
                echo "Image: ${env.IMAGE}"
            }
        }

        stage('Test') {
            // A release only promotes an image that main already tested, built and scanned.
            when { not { buildingTag() } }
            steps {
                // Tests run in a throwaway container, so the Jenkins host needs no Python.
                sh '''
                    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
                        -v "$PWD":/src -w /src python:3.12-slim \
                        sh -c "pip install -q --user -r requirements.txt && python -m pytest -q -p no:cacheprovider"
                '''
            }
        }

        stage('Build image') {
            when { not { buildingTag() } }
            steps {
                sh 'docker build --pull -t "$IMAGE" .'
            }
        }

        stage('Security scan (Trivy)') {
            when { not { buildingTag() } }
            steps {
                // Gate: HIGH/CRITICAL vulnerabilities with an available fix fail the build.
                sh 'trivy image --no-progress --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE"'
            }
        }

        // Optional hook for next week's AI agent (PR review / failure triage). Off by default.
        stage('AI review (optional)') {
            when { allOf { not { buildingTag() }; expression { params.RUN_AI_REVIEW } } }
            steps {
                echo 'AI agent stage placeholder: added in the AI week.'
            }
        }

        stage('Push to ECR') {
            // Only main producePs deployable images; PR/feature branches stop after the scan.
            when { branch 'main' }
            steps {
                // Credentials come from the instance IAM role: no keys stored anywhere.
                sh '''
                    aws ecr get-login-password --region eu-west-1 \
                        | docker login --username AWS --password-stdin "$(echo "$IMAGE" | cut -d/ -f1)"

                    # Tags are immutable: re-running the same commit must skip the push, not fail.
                    if aws ecr describe-images --region eu-west-1 --repository-name weatherapp \
                           --image-ids imageTag="$IMAGE_TAG" >/dev/null 2>&1; then
                        echo "Image $IMAGE_TAG already exists in ECR, skipping push"
                    else
                        docker push "$IMAGE"
                    fi
                '''
            }
        }

        stage('Update GitOps repo') {
            when { branch 'main' }
            steps {
                withCredentials([gitUsernamePassword(credentialsId: 'gitlab-gitops-bot')]) {
                    sh 'rm -rf gitops && git clone --depth 1 https://gitlab.manovaturi.com/weatherapp/weatherapp-gitops.git gitops'
                    dir('gitops') {
                        script {
                            // Dev only: prod's tag changes by merge request
                            def f = 'apps/weatherapp/envs/dev/values.yaml'
                            def line = "  tag: \"${env.IMAGE_TAG}\""
                            def updated = readFile(f).replaceAll(/(?m)^  tag: .*/, line)
                            // replaceAll does nothing when the line is missing, so fail
                            if (!updated.contains(line)) { error("No '  tag:' line found in ${f}") }
                            writeFile file: f, text: updated
                        }
                        sh '''
                            git config user.name jenkins
                            git config user.email jenkins@manovaturi.com
                            # rebase and retry once if gitops moved
                            git diff --quiet || {
                                git commit -am "Bump weatherapp dev image to $IMAGE_TAG" &&
                                { git push origin HEAD:main || { git pull --rebase origin main && git push origin HEAD:main; }; }
                            }
                        '''
                    }
                }
            }
            post { always { sh 'rm -rf gitops' } }
        }

        // Release: a tag vX.Y.Z promotes the image main built, nothing is rebuilt
        stage('Release') {
            when { tag pattern: 'v\\d+\\.\\d+\\.\\d+', comparator: 'REGEXP' }
            steps {
                withCredentials([gitUsernamePassword(credentialsId: 'gitlab-gitops-bot')]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        REGION=eu-west-1
                        REPO=weatherapp
                        digest() { aws ecr describe-images --region "$REGION" --repository-name "$REPO" --image-ids imageTag="$1" --query 'imageDetails[0].imageDigest' --output text 2>/dev/null || true; }

                        # the image main built for this commit must exist
                        BUILT="$(digest "$IMAGE_TAG")"
                        if [ -z "$BUILT" ] || [ "$BUILT" = None ]; then
                            echo "There is no image $IMAGE_TAG in ECR. Tag a commit that main has already built." >&2
                            exit 1
                        fi

                        # add the version name to that same image
                        NAMED="$(digest "$VERSION")"
                        if [ -z "$NAMED" ] || [ "$NAMED" = None ]; then
                            MANIFEST="$(aws ecr batch-get-image --region "$REGION" --repository-name "$REPO" --image-ids imageTag="$IMAGE_TAG" --query 'images[0].imageManifest' --output text)"
                            aws ecr put-image --region "$REGION" --repository-name "$REPO" --image-tag "$VERSION" --image-manifest "$MANIFEST" >/dev/null
                            echo "Image $IMAGE_TAG is now also tagged $VERSION"
                        elif [ "$NAMED" != "$BUILT" ]; then
                            echo "Version $VERSION already names a different image. Pick a new version." >&2
                            exit 1
                        else
                            echo "Image $IMAGE_TAG already has the tag $VERSION"
                        fi

                        # open a merge request that sets prod's tag
                        rm -rf gitops mr_url.txt push.log
                        git clone --depth 1 https://gitlab.manovaturi.com/weatherapp/weatherapp-gitops.git gitops
                        cd gitops
                        git config user.name jenkins
                        git config user.email jenkins@manovaturi.com
                        if git ls-remote --exit-code --heads origin "promote-$VERSION" >/dev/null 2>&1; then
                            echo "The branch promote-$VERSION already exists: its merge request is the promotion."
                            exit 0
                        fi
                        if grep -q "^  tag: \"$VERSION\"" apps/weatherapp/envs/prod/values.yaml; then
                            echo "Production already runs $VERSION."
                            exit 0
                        fi
                        sed -i -E "s/^  tag: .*/  tag: \"$VERSION\"/" apps/weatherapp/envs/prod/values.yaml
                        # sed does nothing when the line is missing, so check
                        grep -q "^  tag: \"$VERSION\"$" apps/weatherapp/envs/prod/values.yaml || { echo "No '  tag:' line found in apps/weatherapp/envs/prod/values.yaml" >&2; exit 1; }
                        git checkout -q -b "promote-$VERSION"
                        git commit -qam "Promote weatherapp $VERSION to production"
                        git push origin "promote-$VERSION" \
                            -o merge_request.create -o merge_request.target=main \
                            -o "merge_request.title=Promote weatherapp $VERSION to production" \
                            -o merge_request.remove_source_branch 2>&1 | tee ../push.log
                        grep -o 'https://[^ ]*merge_requests/[0-9]*' ../push.log | head -1 > ../mr_url.txt || true
                    '''
                }
                script { env.MR_URL = fileExists('mr_url.txt') ? readFile('mr_url.txt').trim() : '' }
            }
            post { always { sh 'rm -rf gitops push.log mr_url.txt' } }
        }
    }

    post {
        success {
            script {
                if (env.TAG_NAME) {
                    notify('good', ":rocket: Release ${env.TAG_NAME}: merge the promotion to put it in production ${env.MR_URL ?: '(open the gitops repo merge requests)'}")
                } else {
                    notify('good', ":white_check_mark: Build succeeded: `${env.IMAGE}`")
                }
            }
        }
        failure { notify('danger', ':x: Build FAILED') }
        always {
            // Don't let old images fill the 30 GB disk.
            sh 'docker image rm "$IMAGE" >/dev/null 2>&1 || true; docker image prune -f >/dev/null 2>&1 || true'
        }
    }
}
