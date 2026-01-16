#!/bin/bash
set -e

# 检查配置文件
if [ ! -f "/app/config/config.yaml" ]; then
    echo "❌ 配置文件 config.yaml 缺失"
    exit 1
fi

if [ ! -f "/app/config/frequency_words.txt" ]; then
    if [ -f "/app/config/frequency_words.txt.template" ]; then
        echo "💡 frequency_words.txt 缺失，正在从模板初始化..."
        cp /app/config/frequency_words.txt.template /app/config/frequency_words.txt
    else
        echo "❌ 配置文件 frequency_words.txt 且模板均缺失"
        exit 1
    fi
fi
    echo "✅ 配置文件检查通过"

# 保存环境变量
env >> /etc/environment

case "${RUN_MODE:-cron}" in
"once")
    echo "🔄 单次执行"
    exec python -m trendradar
    ;;
"cron")
    # 生成 crontab
    # 生成 crontab
    rm -f /tmp/crontab
    # 支持使用 ; 分隔多个定时任务表达式
    IFS=';' read -ra SCHEDULES <<< "${CRON_SCHEDULE:-*/30 * * * *}"
    for schedule in "${SCHEDULES[@]}"; do
        # 去除首尾空白
        schedule=$(echo "$schedule" | xargs)
        if [ -n "$schedule" ]; then
            echo "$schedule cd /app && python -m trendradar" >> /tmp/crontab
        fi
    done

    
    echo "📅 生成的crontab内容:"
    cat /tmp/crontab

    if ! /usr/local/bin/supercronic -test /tmp/crontab; then
        echo "❌ crontab格式验证失败"
        exit 1
    fi

    # 立即执行一次（如果配置了）
    if [ "${IMMEDIATE_RUN:-false}" = "true" ]; then
        echo "▶️ 立即执行一次"
        python -m trendradar
    fi

    # 启动 Web 服务器（如果配置了）
    if [ "${ENABLE_WEBSERVER:-false}" = "true" ]; then
        echo "🌐 启动 Web 服务器..."
        python manage.py start_webserver
    fi

    echo "⏰ 启动supercronic: ${CRON_SCHEDULE:-*/30 * * * *}"
    echo "🎯 supercronic 将作为 PID 1 运行"

    exec /usr/local/bin/supercronic -passthrough-logs /tmp/crontab
    ;;
*)
    exec "$@"
    ;;
esac