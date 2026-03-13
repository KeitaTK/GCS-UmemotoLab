# ドキュメント記述ガイド

別の作業者が見ても分かるドキュメントを生成するための記述方針です。

## 目次

1. [docstring フォーマット](#docstring-フォーマット)
2. [モジュール説明](#モジュール説明)
3. [クラス説明](#クラス説明)
4. [関数/メソッド説明](#関数メソッド説明)
5. [例とベストプラクティス](#例とベストプラクティス)
6. [自動ドキュメント生成](#自動ドキュメント生成)

---

## docstring フォーマット

このプロジェクトは **Numpy形式のdocstring** を採用しています。

### 理由

- 日本語説明が読みやすい
- Parameters/Returns/Raises セクションが明確
- Sphinx + Napoleon拡張で自動的にHTML変換される

---

## モジュール説明

ファイルの先頭に、モジュール全体の説明を書きます。

### テンプレート

```python
"""
module_name - 何をするモジュールか（1行要約）

詳細な説明...
複数行でモジュールの目的・機能を説明します。

Submodules
----------
（サブモジュールがあれば記載）

Examples
--------
>>> from module_name import some_function
>>> result = some_function(arg)
>>> print(result)

See Also
--------
related_module : 関連するモジュール
"""
```

### 例

```python
# app/mavlink/__init__.py
"""
mavlink - MAVLink通信・RTK補正・機体制御モジュール

このパッケージは、ArduPilot（Pixhawk）との通信・制御に関する機能を提供します。

Submodules
----------
connection : MAVLink接続管理
    - UDP/Serial接続管理
    
message_router : メッセージ中継
    - メッセージ解析・分類
"""
```

---

## クラス説明

### テンプレート

```python
class MyClass:
    """
    クラスの名前と短い説明（1行）
    
    詳細な説明：
    - 何をするクラスか
    - どのような場合に使うのか
    - 主な機能は何か
    
    Parameters
    ----------
    param1 : type
        説明
    param2 : type, optional
        説明。デフォルト値: value
    
    Attributes
    ----------
    attr1 : type
        属性の説明
    attr2 : type
        属性の説明
    
    Examples
    --------
    >>> obj = MyClass(param1=value)
    >>> result = obj.method()
    
    Notes
    -----
    - 注意点1
    - 注意点2
    
    See Also
    --------
    RelatedClass : 関連クラス
    """
    
    def __init__(self, param1, param2=default_value):
        ...
```

### 実例（RTCMInjector）

```python
class RtcmInjector:
    """
    RTCM3データをMAVLink GPS_RTCM_DATA でドローンに送信します。
    
    大容量のRTCM補正データ（RTK座標補正情報）を自動分割し、
    複数のGPS_RTCM_DATAメッセージとして送信します。
    
    Parameters
    ----------
    enabled : bool, optional
        RTCMインジェクション機能の有効/無効。デフォルト: True
    max_payload_size : int, optional
        1フレームあたりのペイロード最大サイズ（バイト）。デフォルト: 180
    system_id : int, optional
        送信元のシステムID。デフォルト: 1
    component_id : int, optional
        送信元のコンポーネントID。デフォルト: 1
    
    Attributes
    ----------
    enabled : bool
        機能の有効/無効状態
    stats : dict
        送信統計情報
        - 'rtcm_messages_sent': 送信したRTCMメッセージ数
        - 'mavlink_messages_sent': 送信したMAVLinkメッセージ数
        - 'bytes_sent': 送信したバイト数合計
    
    Examples
    --------
    >>> injector = RtcmInjector(enabled=True)
    >>> injector.set_send_callback(my_send_func)
    >>> injector.inject(rtcm_data)
    >>> print(injector.stats)
    {'rtcm_messages_sent': 1, 'mavlink_messages_sent': 2, 'bytes_sent': 250}
    
    Notes
    -----
    - `set_send_callback()` で送信関数を登録しないと inject() は動作しません
    - 大容量データは自動で分割されますが、各チャンク送信には時間遅延があります
    - 統計情報は送信成功時のみカウントされます
    
    See Also
    --------
    RtcmReader : RTCMデータ受信クラス
    MavlinkConnection : 送受信の実装
    """
```

---

## 関数/メソッド説明

### テンプレート

```python
def my_function(arg1, arg2, arg3=default):
    """
    関数の短い説明（1行）
    
    詳細な説明：
    - 何をする関数か
    - どのような入力を受け取るか
    - どのような出力を返すか
    
    Parameters
    ----------
    arg1 : type
        説明。形式についての詳細も記載。
        例：RTCM v3フォーマットのバイナリデータ
    arg2 : type
        説明
    arg3 : type, optional
        説明。デフォルト: default_value
    
    Returns
    -------
    return_type
        戻り値の説明。
        複数行で詳しく説明する場合はインデント。
    
    Raises
    ------
    ExceptionType
        どのような場合にこの例外が発生するか
    AnotherException
        別の例外とその条件
    
    Examples
    --------
    >>> result = my_function(arg1_value, arg2_value)
    >>> print(result)
    expected_output
    
    >>> # エラーケース
    >>> result = my_function(invalid_input)
    Traceback (most recent call last):
        ...
    ValueError: 説明
    
    Notes
    -----
    - 注意点1
    - 注意点2
    - 処理が非同期の場合はその旨を記載
    
    See Also
    --------
    related_function : 関連関数
    OtherClass.method : 関連メソッド
    """
    ...
```

### 実例（inject メソッド）

```python
def inject(self, rtcm_data: bytes) -> bool:
    """
    RTCMデータをPixhawkに送信します。
    
    大容量のRTCM補正データを複数のGPS_RTCM_DATAフレームに
    自動分割し、すべてのドローンへブロードキャストします。
    
    Parameters
    ----------
    rtcm_data : bytes
        RTCM v3フォーマットのバイナリデータ。
        U-Bloxの u-center から取得したRTCM3ストリーム、
        またはNtripキャスターからの補正データなど。
        最大サイズ: 任意（1400バイト以上推奨）
    
    Returns
    -------
    bool
        送信成功時は True。以下の場合は False:
        
        - inject が disabled 状態
        - send_callback が設定されていない
        - rtcm_data が空
        - 送信中にエラーが発生
    
    Raises
    ------
    TypeError
        rtcm_data が bytes でない場合
    
    Examples
    --------
    >>> injector = RtcmInjector(enabled=True)
    >>> injector.set_send_callback(send_callback_func)
    >>> rtcm_bytes = b'\\xd3\\x00\\x13...'  # RTCM v3フレーム
    >>> success = injector.inject(rtcm_bytes)
    >>> if success:
    ...     print(f"送信成功: {injector.stats['bytes_sent']} bytes")
    
    Notes
    -----
    - ドローンが複数いる場合、全ドローンに同じRTCMデータが送信されます
    - インジェクションは非同期で実行されるため、返却直後に
      すべてのドローンで受信完了とは限りません
    - シーケンス番号は自動で管理されます
    - エラーが発生した場合は logs/gcs.log に詳細が記録されます
    
    See Also
    --------
    set_send_callback : 送信関数の登録
    RtcmReader : RTCMデータ受信クラス
    """
    if not self.enabled or not self.send_callback:
        return False
    ...
```

---

## 例とベストプラクティス

### ✅ 良い例

```python
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    2つの緯度経度座標間の距離（メートル）を計算します。
    
    ハバーサイン公式を使用して地球上の大円距離を計算します。
    
    Parameters
    ----------
    lat1 : float
        最初の座標の緯度（-90〜90度）
    lon1 : float
        最初の座標の経度（-180〜180度）
    lat2 : float
        次の座標の緯度（-90〜90度）
    lon2 : float
        次の座標の経度（-180〜180度）
    
    Returns
    -------
    float
        2点間の距離（メートル）。
        精度: 約0.5%（地形変化は考慮しない）
    
    Raises
    ------
    ValueError
        緯度が -90〜90 度の範囲外の場合
    ValueError
        経度が -180〜180 度の範囲外の場合
    
    Examples
    --------
    >>> # 東京（35.6762°N, 139.6503°E）
    >>> # 大阪（34.6937°N, 135.5023°E）
    >>> dist = calculate_distance(35.6762, 139.6503, 34.6937, 135.5023)
    >>> print(f"距離: {dist:.0f} m")
    距離: 399393 m
    
    Notes
    -----
    - 地球の半径は 6371000 m と仮定
    - ドローンの飛行計画距離計算に使用
    """
```

### ❌ 悪い例

```python
def calc_dist(lat1, lon1, lat2, lon2):
    """距離を計算"""
    # パラメータ説明なし
    # 戻り値の説明なし
    # 使用例なし
    # 注意点なし
```

---

## 自動ドキュメント生成

### ビルドコマンド

```bash
# ローカルでビルド
./scripts/build_docs.sh

# ブラウザで表示
open docs_sphinx/build/html/index.html

# キャッシュをクリアして再ビルド
./scripts/build_docs.sh -r
```

### GitHub Actions（自動生成）

プッシュ時に自動実行：`.github/workflows/docs.yml` を参照

---

## チェックリスト

コードを書いた後、以下のチェックリストで確認してください：

- [ ] モジュール・クラス・関数にdocstringがある
- [ ] 説明は「何をするか」を明確に書いている
- [ ] Parameters/Returns/Raises セクションが完全
- [ ] 実例コードが含まれている
- [ ] 型ヒント（`: type`）が記載されている
- [ ] 注意点（Notes）や関連機能（See Also）がある場合は記載
- [ ] ドキュメント生成後に HTML で確認した

---

## 質問や修正

ドキュメント記述に関する質問があれば、Issueを作成するか、チームに相談してください。

**ドキュメントの質が上がれば、新しいチームメンバーのオンボーディングも楽になります！**
