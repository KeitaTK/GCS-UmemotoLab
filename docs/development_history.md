# 開発履歴

### 2026-07-08 11:25: Kanban passcode authentication bypass
- 問題: `--no-passcode` を指定しているにも関わらず、ブラウザに「Remote Access - Enter the passcode to continue」と表示されパスコード入力が要求された。
- 調査: `--no-passcode` フラグは `launchFlags` Set に含まれており正しく認識されるが、`passcodeEnabled` の初期値が `true` のままであり、`disablePasscode()` が呼ばれる前にリクエストが処理されるタイミングで認証チェックが走っていた。さらに `passcodeEnabled = true` が2箇所（宣言時とモジュール初期化時）に存在した。
- 試行: `patch_kanban_cli.js` に Patch 3 を追加し、`passcodeEnabled = true;` の全出現を正規表現 `g` フラグで `passcodeEnabled = false;` に置換。`/api/passcode/status` が `{"required":true}` ではなく `{"required":false,"authenticated":true}` を返すことをコンテナ内から確認。
- 結果: パスコード認証が完全に無効化され、ログイン画面なしで kanban ボードに直接アクセス可能になった。
- 備考: ログにはパスコードが表示され続けるが、認証自体はバイパスされている。

### 2026-07-08 10:57: Kanban CORS origin check bypass
- 問題: タブに「KANBAN」と表示されるが画面が真っ白。CSS/JSアセット(`/assets/*`)が全て HTTP 403 Forbidden でブロックされていた。
- 調査: kanban パッケージの `cli.js` を解析。`handleHttpRequest()` 内の `evaluateCors()` が `origin !== input.allowedOrigin` で拒否していることを特定。`--host 0.0.0.0` で起動しているため、許可オリジンが `http://0.0.0.0:3484` なのに対し、実際のアクセス元（Tailscale IP `http://100.105.70.118:3484`）が不一致で 403 になっていた。
- 試行: `scripts/patch_kanban_cli.js` を拡張し、Host 検証に加えて CORS の origin チェック (`if (origin !== input.allowedOrigin && !isDevServer)`) も `if (false)` に置換するパッチを追加。
- 結果: パッチ適用後、コンテナ内部からのテストでアセットが HTTP 200 で正常応答することを確認。kanban ボードが正常表示されるようになった。
- 備考: `npm install -g kanban` によって再インストールされるたびにパッチが必要なため、`patch_kanban_cli.js` は idempotent（再実行安全）に設計した。

### 2026-07-07 20:51: Kanban host validation bypass
- 問題: localhost:3485 でのアクセスが HTTP 403 Forbidden で拒否されていた。
- 調査: Kanban の host 検証ロジック (`evaluateHost()`) を確認し、Host ヘッダーが「許可リスト」に存在しない場合に拒否していることを確認した。
- 試行: `patch_kanban_cli.js` を修正し、host 検証チェック (`if (hostDecision.kind === "reject")`) を条件付きで無効化 (`if (false)`) する方法に変更した。
- 結果: ホスト名検証を完全に無効化し、すべてのアクセスを許可するように改善。localhost:3485 での接続成功を確認（HTTP 200）。
- 備考: 本修正により、Tailscale 経由や localhost のいずれからのアクセスも受け入れるようになった。

### 2026-07-07 12:27: Kanban/Tailscale
- 問題: docker compose で起動する kanban コンテナが Node 20 のため、@clinebot 系パッケージの required engine と一致せず警告が出ていた。
- 調査: docker-compose.yml の kanban サービス定義と起動ログを確認し、現在のベースイメージが node:20-slim であることを確認した。
- 試行: kanban サービスの image を node:22-slim に更新し、起動コマンドを 127.0.0.1 バインドへ変更した。
- 結果: Node 22 系で起動する構成に更新し、Tailscale の共有名前空間内での接続先を明示した。
- 備考: 既存の tailscale サービス定義は維持した。

### 2026-07-07 12:27: Kanban listen port
- 問題: kanban コンテナは起動していたが、3485 では接続拒否になった。
- 調査: コンテナ内で `kanban --help` を確認し、Runtime URL が 127.0.0.1:3484 と表示されることを確認した。
- 試行: `docker-compose.yml` の kanban 起動ポートを 3484 に修正した。
- 結果: 実際の runtime port と compose 設定を一致させた。
- 備考: bind host は 127.0.0.1 のまま維持した。

### 2026-07-07 12:27: Kanban host validation
- 問題: MacBook から Tailscale の公開 URL を開くと `Host not allowed` になった。
- 調査: Kanban の `dist/cli.js` を確認し、`evaluateHost()` が `allowedHosts` の完全一致で Host ヘッダーを検証していることを確認した。
- 試行: コンテナ起動時に Kanban の CLI を軽くパッチし、Tailscale 公開ホスト名と `:443` を許可対象に追加するようにした。
- 結果: Tailscale Serve 経由の公開ホストを受け入れる前提を追加した。
- 備考: 既存の localhost/127.0.0.1 の許可は維持した。

### 2026-07-07 12:27: Kanban startup patch script
- 問題: 起動コマンド内の heredoc が `sh` で解釈エラーになった。
- 調査: `docker compose logs` で `Syntax error: ( unexpected` を確認し、シェル文法が原因と判断した。
- 試行: Host 許可のパッチ処理を [scripts/patch_kanban_cli.js](/home/nambu/GCS-UmemotoLab/scripts/patch_kanban_cli.js) に分離し、compose の起動コマンドを単純化した。
- 結果: 起動時に CLI を補正する処理を外出しし、シェル構文依存を減らした。
- 備考: パッチ対象は Kanban のローカルインストール済み CLI に限定した。