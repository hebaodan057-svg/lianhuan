#!/bin/sh
# 造一把安卓签名钥匙。跑一次就够，之后一直用它。
#
# 为什么单独写成脚本：
#   keytool 是 JVM 程序，在 proot 里冷启动要十几秒，还可能在第一次运行时
#   生成 /dev/random 的熵池。直接塞在一条长命令里，容易被终端判超时打断，
#   打断到一半的 keystore 是**坏的**，而且看起来像存在了。
#   所以：独立进程 + 输出重定向到日志，跑完再看结果。
set -e

KS="$HOME/.lianhuan/lianhuan.jks"
PW="${LH_KS_PASS:?需要 LH_KS_PASS 环境变量}"
ALIAS="lianhuan"

mkdir -p "$HOME/.lianhuan"

# ★ 先删旧的：不能"覆盖"生成，keytool 会问你"要覆盖吗"，那头是死等
rm -f "$KS"

keytool -genkeypair \
  -keystore "$KS" \
  -alias "$ALIAS" \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storepass "$PW" \
  -keypass "$PW" \
  -dname "CN=lianhuan, OU=self, O=self, L=self, ST=self, C=CN" \
  > "$HOME/.lianhuan/gen.log" 2>&1

echo "GEN_OK"
