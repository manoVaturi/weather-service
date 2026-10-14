def AWS_REGION = 'eu-west-1'
def ECR_REGISTRY = '://amazonaws.com'
def IMAGE_REPO = 'weatherapp'

// Slack must never be able to fail a build, so every call is wrapped.
def notify(String color, String text) {
    try {
        slackSend(channel: '#devops', color: color, tokenCredentialId: 'slack-token',
                  message: "\({text}\n\){env.JOB_NAME} #\({env.BUILD_NUMBER} (<\){env.BUILD_URL}|open>)")
    } catch (err) {
        echo "Slack notification skipped: \${err.message}"
    }
}

pipeline {
    agent any

    environment {
        // Binds the secure Jenkins credential directly to the system variable the CLI expects
        GEMINI_API_KEY = credentials('GEMINI_API_KEY')
    }
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
                script {
                    env.IMAGE_TAG = env.GIT_COMMIT.take(7)
                    env.IMAGE = "\${ECR_REGISTRY}/\({IMAGE_REPO}:\){env.IMAGE_TAG}"
                }
                echo "Image: \${env.IMAGE}"
            }
        }

        stage('Test') {
            steps {
                sh '''
                    docker run --rm -u "(id -u):(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
                        -v "\$PWD":/src -w /src python:3.12-slim \
                        sh -c "pip install -q --user -r requirements.txt && python -m pytest -q -p no:cacheprovider"
                '''
            }
        }

        stage('Build image') {
            steps {
                sh 'docker build --pull -t "\$IMAGE" .'
            }
        }

        stage('Security scan (Trivy)') {
            steps {
                sh 'trivy image --no-progress --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "\$IMAGE"'
            }
        }

        // Active Gemini AI agent stage for automated review, branching, and pushing
        stage('AI review (optional)') {
            when { expression { params.RUN_AI_REVIEW } }
            steps {
                // Using withCredentials or native ssh-agent block if your Jenkins SCM job configuration uses SSH keys
                script {
                    echo 'Starting automated Gemini code review and PR preparation...'

                    // Configure git actor names for the automated review commit
                    sh 'git config user.name "Jenkins Gemini Agent"'
                    sh 'git config user.email "jenkins-ai-agent@internal.local"'

                    // Create a unique review branch name based on the build number
                    def branchName = "gemini-review-\${env.BUILD_NUMBER}"
                    sh "git checkout -b \${branchName}"

                    // Run Gemini CLI through a container to review files and modify them
                    sh """
                        docker run --rm -v "\$PWD":/src -w /src node:20-alpine \
                            npx -y @google/genai-cli review \
                            --api-key="\${env.GEMINI_API_KEY}" \
                            --dir="." \
                            --apply-fixes
                    """

                    // Check if Gemini actually made any code optimization modifications
                    def hasChanges = sh(script: "git status --porcelain", returnStatus: true) == 0 ? false : true

                    if (hasChanges) {
                        echo "Gemini discovered optimization fixes. Committing changes..."
                        sh "git add ."
                        sh "git commit -m 'chore(ai): automated code quality and security fixes from Gemini'"

                        // Push up the new branch. Since GitHub is pre-configured in the job/SCM setup,
                        // Jenkins handles the authentication variables automatically behind the scenes.
                        sh "git push origin \${branchName}"
                        echo "Branch \${branchName} successfully pushed to GitHub! You can now open a Pull Request."
                    } else {
                        echo "Gemini reviewed the code and found no necessary optimization fixes."
                    }
                }
            }
        }

        stage('Push to ECR') {
            when { branch 'main' }
            steps {
                sh '''
                    aws ecr get-login-password --region eu-west-1 \

                        | docker login --username AWS --password-stdin "(echo "IMAGE" | cut -d/ -f1)"

                    if aws ecr describe-images --region eu-west-1 --repository-name weatherapp \
                           --image-ids imageTag="\$IMAGE_TAG" >/dev/null 2>&1; then
                        echo "Image \$IMAGE_TAG already exists in ECR, skipping push"
                    else
                        docker push "\$IMAGE"
                    fi
                '''
            }
        }
    }

    post {
        success {
            notify('good', ":white_check_mark: Build succeeded: `${env.IMAGE}`")
        }
        failure {
            notify('danger', ':x: Build FAILED')
            aiAgent(
                agent: geminiCli(),
                apiCredentialsId: 'GEMINI_API_KEY',
                prompt: "The Jenkins pipeline failed. Analyze the recent console log outputs, locate the exact stack trace or syntax error that caused the crash, and provide a direct fix.",
                failOnAgentError: false
            )
        }
        always {
            sh 'docker image rm "\$IMAGE" >/dev/null 2>&1 || true; docker image prune -f >/dev/null 2>&1 || true'
        }
    }
}
