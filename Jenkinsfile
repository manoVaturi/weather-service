// WeatherApp CI pipeline (declarative).
// Flow: checkout -> test -> build -> scan (gate) -> push to ECR -> notify.
// Deployment is NOT done here: Argo CD deploys from the gitops repo (Phase 6).
// Webhook is protected by a GitHub shared secret (HMAC signature verified by Jenkins).

def AWS_REGION = 'eu-west-1'
def ECR_REGISTRY = '991776826412.dkr.ecr.eu-west-1.amazonaws.com'
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
                // Done in a stage, not in environment{}: that block runs BEFORE checkout,
                // when GIT_COMMIT does not exist yet.
                script {
                    // The git SHA is the image tag: immutable, traceable, never "latest".
                    env.IMAGE_TAG = env.GIT_COMMIT.take(7)
                    env.IMAGE = "${ECR_REGISTRY}/${IMAGE_REPO}:${env.IMAGE_TAG}"
                }
                echo "Image: ${env.IMAGE}"
            }
        }

        stage('Test') {
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
            steps {
                sh 'docker build --pull -t "$IMAGE" .'
            }
        }

        stage('Security scan (Trivy)') {
            steps {
                // Gate: HIGH/CRITICAL vulnerabilities with an available fix fail the build.
                sh 'trivy image --no-progress --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE"'
            }
        }

        // Optional hook for next week's AI agent (PR review / failure triage). Off by default.
        stage('AI review (optional)') {
            when { expression { params.RUN_AI_REVIEW } }
            steps {
                echo 'AI agent stage placeholder: added in the AI week.'
            }
        }

        stage('Push to ECR') {
            // Only main produces deployable images; PR/feature branches stop after the scan.
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
                withCredentials([gitUsernamePassword(credentialsId: 'gitops-writer')]) {
                    sh 'rm -rf gitops && git clone --depth 1 https://github.com/manoVaturi/weatherapp-gitops.git gitops'
                    dir('gitops') {
                        script {
                            def f = 'charts/weatherapp/values.yaml'
                            writeFile file: f, text: readFile(f).replaceAll(/(?m)^  tag: .*/, "  tag: \"${env.IMAGE_TAG}\"")
                        }
                        sh '''
                            git config user.name jenkins
                            git config user.email jenkins@manovaturi.com
                            git diff --quiet || { git commit -am "Bump weatherapp image to $IMAGE_TAG" && git push origin HEAD:main; }
                        '''
                    }
                }
            }
            post { always { sh 'rm -rf gitops' } }
        }
    }

    post {
        success { notify('good', ":white_check_mark: Build succeeded: `${env.IMAGE}`") }
        failure { notify('danger', ':x: Build FAILED') }
        always {
            // Don't let old images fill the 30 GB disk.
            sh 'docker image rm "$IMAGE" >/dev/null 2>&1 || true; docker image prune -f >/dev/null 2>&1 || true'
        }
    }
}
