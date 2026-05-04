pipeline {
    agent any

    environment {
        // Nginx와 공유되는 Jenkins 내부 배포 경로
        DEPLOY_PATH = "/var/jenkins_home/deploy_to_nginx"
    }

    stages {
        stage('Step 1: 소스 가져오기') {
            steps {
                echo 'GitHub로부터 최신 코드를 가져옵니다.'
                checkout scm
            }
        }

        stage('Step 2: 빌드 및 준비') {
            steps {
                echo '웹 정적 파일을 빌드 폴더(dist)로 모읍니다.'
                // 로컬 환경이므로 무거운 빌드 대신 필요한 파일만 선별하여 복사합니다.
                sh '''
                    mkdir -p dist
                    cp *.html dist/ 2>/dev/null || echo "HTML 파일이 없습니다."
                    cp *.css dist/ 2>/dev/null || echo "CSS 파일이 없습니다."
                    echo "마지막 빌드 시간: $(date)" > dist/build_report.txt
                '''
            }
        }

        stage('Step 3: 로컬 Nginx로 배포') {
            steps {
                echo '공유 볼륨을 통해 Nginx 웹 경로로 파일을 복사합니다.'
                // 기존 배포 폴더가 없다면 생성하고 파일을 복사합니다.
                sh """
                    mkdir -p ${DEPLOY_PATH}
                    cp -r dist/* ${DEPLOY_PATH}/
                """
                echo "배포 완료! http://localhost 에서 확인하세요."
            }
        }
    }

    post {
        success {
            echo '축하합니다! first_item 빌드 및 배포에 성공했습니다.'
        }
        failure {
            echo '빌드 중 오류가 발생했습니다. Jenkins 로그를 확인해 주세요.'
        }
    }
}