#!/bin/sh
# 把钥匙变成两个能直接用的值：
#   ① base64  → GitHub Secret: ANDROID_KEYSTORE_BASE64
#   ② SHA-256 → android-full/SIGNING_FINGERPRINT.txt
set -e

KS="$HOME/.lianhuan/lianhuan.jks"
PW="${LH_KS_PASS:?需要 LH_KS_PASS}"
OUT="$HOME/.lianhuan"

[ -f "$KS" ] || { echo "钥匙不在：$KS"; exit 1; }

# ① 整份文件转 base64，去掉换行 —— Secret 必须是单行
base64 "$KS" | tr -d '\n' > "$OUT/ks.b64"

# ② 指纹：keytool -list -v 输出里找 SHA256 那行，去掉冒号，转小写
keytool -list -v -keystore "$KS" -alias lianhuan -storepass "$PW" 2>/dev/null \
  | grep -i 'SHA256:' \
  | awk '{print $2}' \
  | tr -d ':' \
  | tr 'A-F' 'a-f' > "$OUT/fingerprint.txt"

echo "---- ① base64 ----"
echo "字符数: $(wc -c < "$OUT/ks.b64")"
cat "$OUT/ks.b64"
echo
echo "---- ② 指纹 ----"
cat "$OUT/fingerprint.txt"
echo "字符数: $(wc -c < "$OUT/fingerprint.txt")"
