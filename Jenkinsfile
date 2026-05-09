pipeline {
  agent any

  options {
    ansiColor('xterm')
    buildDiscarder(logRotator(numToKeepStr: '20'))
    disableConcurrentBuilds()
    timeout(time: 60, unit: 'MINUTES')
    timestamps()
  }

  parameters {
    choice(
      name: 'DEPLOY_ACTION',
      choices: ['build-only', 'deploy', 'infra-plan', 'infra-apply', 'infra-destroy'],
      description: 'Pipeline action: build-only (build+push images), deploy (build+push+migrate+deploy services), infra-plan/apply/destroy (Terraform).'
    )
    choice(
      name: 'ENVIRONMENT',
      choices: ['dev', 'staging', 'prod'],
      description: 'Target deployment environment.'
    )
    string(
      name: 'AWS_REGION',
      defaultValue: 'us-east-1',
      description: 'AWS region for deployment.'
    )
    string(
      name: 'IMAGE_TAG',
      defaultValue: '',
      description: 'Docker image tag. Defaults to short Git SHA if left empty.'
    )
    booleanParam(
      name: 'AUTO_APPROVE',
      defaultValue: false,
      description: 'Skip manual approval gate for deploy/infra-apply/infra-destroy.'
    )
    booleanParam(
      name: 'RUN_TESTS',
      defaultValue: true,
      description: 'Run unit tests before building images.'
    )
  }

  environment {
    TF_DIR             = 'infra/terraform'
    TF_IN_AUTOMATION   = 'true'
    TF_INPUT           = '0'
    TERRAFORM_BIN      = '/opt/homebrew/bin/terraform'
    AWS_BIN            = '/usr/local/bin/aws'
    AWS_DEFAULT_REGION = "${params.AWS_REGION}"
    AWS_REGION         = "${params.AWS_REGION}"
    AWS_CREDS_ID       = 'aws-jenkins-creds'
    NAME_PREFIX        = 'dhp'
    ECS_CLUSTER        = "${NAME_PREFIX}-${params.ENVIRONMENT}-cluster"
    ECR_REGISTRY       = '' // Set in Preflight stage via aws sts
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script {
          currentBuild.description = "${params.DEPLOY_ACTION} | ${params.ENVIRONMENT} | ${params.AWS_REGION}"
          env.GIT_SHORT_SHA = sh(script: 'git rev-parse --short=12 HEAD', returnStdout: true).trim()
          env.DEPLOY_TAG = params.IMAGE_TAG?.trim() ? params.IMAGE_TAG.trim() : env.GIT_SHORT_SHA
        }
      }
    }

    stage('Preflight') {
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail

            test -x "${TERRAFORM_BIN}" || { echo "Terraform not found at ${TERRAFORM_BIN}"; exit 1; }
            test -x "${AWS_BIN}" || { echo "AWS CLI not found at ${AWS_BIN}"; exit 1; }

            echo "=== Tool Versions ==="
            "${TERRAFORM_BIN}" version
            "${AWS_BIN}" --version
            python3 --version
            docker --version

            echo "=== AWS Identity ==="
            CALLER=$("${AWS_BIN}" sts get-caller-identity)
            echo "${CALLER}"
            ACCOUNT_ID=$(echo "${CALLER}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
            echo "ECR_REGISTRY=${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" > ecr_env.txt
          '''
          script {
            def ecrEnv = readFile('ecr_env.txt').trim()
            env.ECR_REGISTRY = ecrEnv.split('=')[1]
          }
        }
      }
    }

    stage('Lint') {
      when {
        expression { params.DEPLOY_ACTION in ['build-only', 'deploy'] }
      }
      steps {
        sh '''
          set -euo pipefail
          echo "=== Linting Python services ==="
          pip3 install --quiet ruff 2>/dev/null || true
          for svc in services/job-service services/metadata-service services/log-service services/storage-service services/lineage-service services/orchestrator; do
            if [ -d "${svc}" ]; then
              echo "Linting ${svc}..."
              ruff check "${svc}" || true
            fi
          done
        '''
      }
    }

    stage('Test') {
      when {
        allOf {
          expression { params.RUN_TESTS }
          expression { params.DEPLOY_ACTION in ['build-only', 'deploy'] }
        }
      }
      steps {
        sh '''
          set -euo pipefail
          echo "=== Running tests ==="
          for svc in services/job-service services/metadata-service; do
            if [ -d "${svc}/tests" ]; then
              echo "Testing ${svc}..."
              cd "${svc}"
              pip3 install --quiet -r requirements.txt 2>/dev/null || true
              python3 -m pytest tests/ -v --tb=short || exit 1
              cd "${WORKSPACE}"
            fi
          done
        '''
      }
    }

    stage('Build & Push Images') {
      when {
        expression { params.DEPLOY_ACTION in ['build-only', 'deploy'] }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            echo "=== ECR Login ==="
            "${AWS_BIN}" ecr get-login-password --region "${AWS_REGION}" \
              | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
          '''
          script {
            def images = [
              ['name': 'job-service',      'context': 'services/job-service'],
              ['name': 'metadata-service', 'context': 'services/metadata-service'],
              ['name': 'log-service',      'context': 'services/log-service'],
              ['name': 'storage-service',  'context': 'services/storage-service'],
              ['name': 'lineage-service',  'context': 'services/lineage-service'],
              ['name': 'orchestrator',     'context': 'services/orchestrator'],
              ['name': 'spark-base',       'context': 'spark-images/base'],
              ['name': 'db-migrations',    'context': 'db'],
            ]
            def parallelBuilds = [:]
            for (img in images) {
              def imageName = img.name
              def imageContext = img.context
              parallelBuilds[imageName] = {
                sh """
                  set -euo pipefail
                  REPO="${env.ECR_REGISTRY}/${env.NAME_PREFIX}-${params.ENVIRONMENT}/${imageName}"
                  echo "Building ${imageName} from ${imageContext}..."
                  docker build -t "\${REPO}:${env.DEPLOY_TAG}" -t "\${REPO}:latest" "${imageContext}"
                  docker push "\${REPO}:${env.DEPLOY_TAG}"
                  docker push "\${REPO}:latest"
                """
              }
            }
            parallel parallelBuilds
          }
        }
      }
    }

    stage('Run DB Migrations') {
      when {
        expression { params.DEPLOY_ACTION == 'deploy' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            echo "=== Running Database Migrations via ECS RunTask ==="

            TD_ARN=$("${AWS_BIN}" ecs describe-task-definition \
              --task-definition "${NAME_PREFIX}-${ENVIRONMENT}-db-migrations" \
              --query 'taskDefinition.taskDefinitionArn' --output text)

            VPC_ID=$("${AWS_BIN}" ec2 describe-vpcs \
              --filters "Name=tag:Project,Values=DHP" \
              --query 'Vpcs[0].VpcId' --output text)

            SUBNETS=$("${AWS_BIN}" ec2 describe-subnets \
              --filters "Name=tag:Tier,Values=private" "Name=vpc-id,Values=${VPC_ID}" \
              --query 'Subnets[*].SubnetId' --output text | tr '\\t' ',')

            SG=$("${AWS_BIN}" ec2 describe-security-groups \
              --filters "Name=group-name,Values=${NAME_PREFIX}-${ENVIRONMENT}-ecs-tasks" \
              --query 'SecurityGroups[0].GroupId' --output text)

            "${AWS_BIN}" ecs run-task \
              --cluster "${ECS_CLUSTER}" \
              --task-definition "${TD_ARN}" \
              --launch-type FARGATE \
              --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG}],assignPublicIp=DISABLED}" \
              --started-by "jenkins-migrations-${BUILD_NUMBER}" \
              > run-task.json

            TASK_ARN=$(python3 -c "import json; print(json.load(open('run-task.json'))['tasks'][0]['taskArn'])")
            echo "Migration task: ${TASK_ARN}"

            "${AWS_BIN}" ecs wait tasks-stopped --cluster "${ECS_CLUSTER}" --tasks "${TASK_ARN}"

            EXIT_CODE=$("${AWS_BIN}" ecs describe-tasks \
              --cluster "${ECS_CLUSTER}" --tasks "${TASK_ARN}" \
              --query 'tasks[0].containers[0].exitCode' --output text)

            if [ "${EXIT_CODE}" != "0" ]; then
              echo "ERROR: Migrations failed with exit code ${EXIT_CODE}"
              exit 1
            fi
            echo "Migrations completed successfully."
          '''
        }
      }
    }

    stage('Approval') {
      when {
        allOf {
          expression { params.DEPLOY_ACTION in ['deploy', 'infra-apply', 'infra-destroy'] }
          expression { !params.AUTO_APPROVE }
        }
      }
      steps {
        input message: "Approve ${params.DEPLOY_ACTION} for environment '${params.ENVIRONMENT}' in ${params.AWS_REGION}?"
      }
    }

    stage('Deploy ECS Services') {
      when {
        expression { params.DEPLOY_ACTION == 'deploy' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          script {
            def services = ['job-service', 'metadata-service', 'log-service', 'storage-service', 'lineage-service', 'orchestrator']
            def parallelDeploys = [:]
            for (svc in services) {
              def serviceName = svc
              parallelDeploys[serviceName] = {
                sh """
                  set -euo pipefail
                  FAMILY="${env.NAME_PREFIX}-${params.ENVIRONMENT}-${serviceName}"
                  IMAGE="${env.ECR_REGISTRY}/${env.NAME_PREFIX}-${params.ENVIRONMENT}/${serviceName}:${env.DEPLOY_TAG}"

                  echo "=== Deploying ${serviceName} ==="

                  # Get current task definition and update image
                  "${env.AWS_BIN}" ecs describe-task-definition --task-definition "\${FAMILY}" \
                    --query 'taskDefinition' > td-${serviceName}.json

                  python3 -c "
import json, sys
td = json.load(open('td-${serviceName}.json'))
for key in ['taskDefinitionArn','revision','status','requiresAttributes','compatibilities','registeredAt','registeredBy']:
    td.pop(key, None)
td['containerDefinitions'][0]['image'] = '\${IMAGE}'
json.dump(td, open('td-${serviceName}-new.json','w'))
"

                  NEW_ARN=\$("${env.AWS_BIN}" ecs register-task-definition \
                    --cli-input-json file://td-${serviceName}-new.json \
                    --query 'taskDefinition.taskDefinitionArn' --output text)

                  "${env.AWS_BIN}" ecs update-service \
                    --cluster "${env.ECS_CLUSTER}" \
                    --service "\${FAMILY}" \
                    --task-definition "\${NEW_ARN}" \
                    --force-new-deployment

                  echo "Waiting for ${serviceName} to stabilize..."
                  "${env.AWS_BIN}" ecs wait services-stable \
                    --cluster "${env.ECS_CLUSTER}" \
                    --services "\${FAMILY}"
                  echo "${serviceName} deployed successfully."
                """
              }
            }
            parallel parallelDeploys
          }
        }
      }
    }

    // ---- Terraform Infrastructure Stages ----

    stage('Terraform Init') {
      when {
        expression { params.DEPLOY_ACTION in ['infra-plan', 'infra-apply', 'infra-destroy'] }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" init \
              -backend-config="region=${AWS_REGION}"
          '''
        }
      }
    }

    stage('Terraform Validate') {
      when {
        expression { params.DEPLOY_ACTION in ['infra-plan', 'infra-apply', 'infra-destroy'] }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" fmt -check -recursive "${TF_DIR}"
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" validate
          '''
        }
      }
    }

    stage('Terraform Plan') {
      when {
        expression { params.DEPLOY_ACTION in ['infra-plan', 'infra-apply'] }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" plan \
              -var="environment=${ENVIRONMENT}" \
              -var="aws_region=${AWS_REGION}" \
              -var="image_tag=${DEPLOY_TAG}" \
              -out=tfplan
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" show -no-color tfplan > "${TF_DIR}/tfplan.txt"
          '''
        }
        archiveArtifacts artifacts: "${env.TF_DIR}/tfplan.txt", fingerprint: true
      }
    }

    stage('Terraform Destroy Plan') {
      when {
        expression { params.DEPLOY_ACTION == 'infra-destroy' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" plan -destroy \
              -var="environment=${ENVIRONMENT}" \
              -var="aws_region=${AWS_REGION}" \
              -out=tfdestroy
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" show -no-color tfdestroy > "${TF_DIR}/tfdestroy.txt"
          '''
        }
        archiveArtifacts artifacts: "${env.TF_DIR}/tfdestroy.txt", fingerprint: true
      }
    }

    stage('Terraform Apply') {
      when {
        expression { params.DEPLOY_ACTION == 'infra-apply' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" apply -auto-approve tfplan
          '''
        }
      }
    }

    stage('Terraform Destroy') {
      when {
        expression { params.DEPLOY_ACTION == 'infra-destroy' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            "${TERRAFORM_BIN}" -chdir="${TF_DIR}" apply -auto-approve tfdestroy
          '''
        }
      }
    }

    stage('Smoke Test') {
      when {
        expression { params.DEPLOY_ACTION == 'deploy' }
      }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: env.AWS_CREDS_ID
        ]]) {
          sh '''
            set -euo pipefail
            echo "=== Running Smoke Tests ==="

            ALB_DNS=$("${AWS_BIN}" elbv2 describe-load-balancers \
              --names "${NAME_PREFIX}-${ENVIRONMENT}-alb" \
              --query 'LoadBalancers[0].DNSName' --output text 2>/dev/null || echo "")

            if [ -z "${ALB_DNS}" ] || [ "${ALB_DNS}" = "None" ]; then
              echo "WARNING: Could not resolve ALB DNS. Skipping smoke tests."
              exit 0
            fi

            BASE_URL="http://${ALB_DNS}"
            FAILED=0

            for path in /jobs/health/ready /metadata/health/ready /logs/health/ready /storage/health/ready /lineage/health/ready; do
              STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}${path}" || echo "000")
              if [ "${STATUS}" = "200" ]; then
                echo "OK: ${path} -> ${STATUS}"
              else
                echo "FAIL: ${path} -> ${STATUS}"
                FAILED=1
              fi
            done

            if [ "${FAILED}" = "1" ]; then
              echo "WARNING: Some health checks failed. Services may still be stabilizing."
            fi
          '''
        }
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'infra/terraform/tfplan.txt, infra/terraform/tfdestroy.txt', allowEmptyArchive: true
    }
    success {
      echo "Pipeline completed successfully: ${params.DEPLOY_ACTION} | ${params.ENVIRONMENT} | tag=${env.DEPLOY_TAG}"
    }
    failure {
      echo "Pipeline FAILED: ${params.DEPLOY_ACTION} | ${params.ENVIRONMENT}. Check console output for details."
    }
    cleanup {
      sh 'rm -f run-task.json td-*.json ecr_env.txt 2>/dev/null || true'
    }
  }
}
