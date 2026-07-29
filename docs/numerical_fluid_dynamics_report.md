# 数値流体力学 レポート課題

**学籍番号**:26720159

**所属**: 安全社会基盤工学専攻機械設計工学コース

**氏名**:南部 太陽

**推敲回数**: 2

---

## 問1 第4章「移流方程式の数値シミュレーション（上流差分）」(25点)

### 1.1 数値振動とは何か

**数値振動**とは、実際の物理現象とは無関係に、数値解析法の性質に起因して発達する高周波な変動のことである。

ある物理量の初期分布が移流する場合、その値は時間発展しても初期分布の最大値を越えたり最小値を下回ったりすることは物理的にありえない。しかし、数値シミュレーションで差分計算を実行すると、たとえ時間進行計算の安定条件を満たしていても、非物理的な「オーバーシュート」や「アンダーシュート」が生じることがある。例えば質量やエネルギーが負になったり、キャビテーションの気相体積率が$[0,1]$の範囲を逸脱したりする。このような現象が発生した瞬間、数値シミュレーションの継続が不可能になるか、計算結果が無意味になる。

具体的な例として、1次元移流方程式

$$
\frac{\partial u}{\partial t} + c\frac{\partial u}{\partial x} = 0 \quad (c > 0)
$$
を時間前進差分・空間中心差分

$$
\frac{u_j^{n+1} - u_j^n}{\Delta t} + c\frac{u_{j+1}^n - u_{j-1}^n}{2\Delta x} = 0
$$
で離散化した場合、フォン・ノイマンの安定性解析により増幅率 $|G| = \sqrt{1 + \nu^2 \sin^2(k\Delta x)}$（$\nu = c\Delta t/\Delta x$ はクーラン数）は常に $|G| > 1$ となり、**無条件不安定**で格子スケールの数値振動が発生する。数値シミュレーションの信頼性を維持するためには、これらの現象をできる限り発生させないよう注意しなければならない。

### 1.2 風上差分とは何か

**風上差分**（上流差分）とは、移流方程式の空間微分を、流速の符号で判断された風上側の2点の物理量を用いて離散化する手法である。

移流方程式

$$
\frac{\partial \phi}{\partial t} = -u\frac{\partial \phi}{\partial x}
$$
において、移流速度 $u$ が一定で物理量の初期分布が孤立波の場合、厳密解は初期分布の形状を維持したまま移流速度で移動する。これを数値解析で解く際、流速 $u$ の符号に応じて風上側の値を用い、次のように離散化する：

$$
\phi_i^{n+1} = \begin{cases}
\displaystyle \phi_i^n - \Delta t\,u\,\frac{\phi_i^n - \phi_{i-1}^n}{\Delta x} & (u \geq 0) \\[12pt]
\displaystyle \phi_i^n - \Delta t\,u\,\frac{\phi_{i+1}^n - \phi_i^n}{\Delta x} & (u < 0)
\end{cases}
$$
この計算方法を**風上差分**という。風上差分は、物理的な情報伝播の方向（上流から下流）に従って差分を取る点が本質である。フォン・ノイマンの安定性解析により、増幅率は

$$
|G| = \sqrt{1 - 4\nu(1-\nu)\sin^2\left(\frac{k\Delta x}{2}\right)}
$$
となり、クーラン数 $\nu = |u|\Delta t/\Delta x$ が $0 \leq \nu \leq 1$ のとき $|G| \leq 1$ が保証され、**条件付き安定**となる。すなわち、風上差分は数値振動を抑制できる。

### 1.3 数値拡散、数値粘性とは何か

**数値拡散**（数値粘性）とは、風上差分による離散化によって導入される、元の微分方程式には含まれていない人工的な拡散（粘性）効果である。

風上差分による数値解がなまる理由を調べるため、移流項の風上差分（$u \geq 0$ の場合）をテイラー展開を用いて位置 $i$ の値で書き直すと、

$$
\begin{aligned}
-u\frac{\phi_i^n - \phi_{i-1}^n}{\Delta x}
&= -\frac{u}{\Delta x}\left\{ \phi_i^n - \left( \phi_i^n - \Delta x\left.\frac{\partial\phi}{\partial x}\right|_i^n + \frac{\Delta x^2}{2}\left.\frac{\partial^2\phi}{\partial x^2}\right|_i^n - \cdots \right) \right\} \\[6pt]
&= -u\left.\frac{\partial\phi}{\partial x}\right|_i^n + \frac{u\Delta x}{2}\left.\frac{\partial^2\phi}{\partial x^2}\right|_i^n - \cdots
\end{aligned}
$$
となる。右辺の誤差項の最低次数は $\Delta x$ の1次であるから、風上差分は**1次精度**である。この誤差項の中で主要な1次項は物理量 $\phi$ の2階の空間微分であり、物理的には拡散の効果を持つ。このときの拡散係数は

$$
\frac{u\Delta x}{2}
$$
である。この効果は元の微分方程式には含まれておらず、風上差分による離散化によって加えられたものである。数値計算法に依存して導入された拡散効果であることから、これを**数値拡散**あるいは**人工拡散**という。また、流れの数値シミュレーションでは、実際の物理的な粘性とは別に**数値粘性**が働いていると言うこともある。

数値拡散により、特にクーラン数が小さい場合に解のピークが鈍る（なまる）という副作用が生じる。数値振動を抑制できる利点と、解の精度を低下させる欠点のトレードオフが存在する。

---

## 問2 第5章「非圧縮性流れの数値解析法（MAC系解法）」(25点, 内★5点)

### 2.1 MAC系解法にどのような数値解析法があるか

MAC系解法とは、MAC法（Marker and Cell法, Harlow & Welch, 1965）を源流とする非圧縮性流れの数値解析手法群である。主な解法を以下に示す。

- **MAC法**
- **SMAC法**
- **HSMAC法**
- **Fractional Step法**
- **SIMPLE法**

また，これに関連する方法として，圧縮性流れと非圧縮性流れを統一的に解析できる**ICE（Implicit Continuous-fluid Eulerian）法** ★，移動や変形する物体周りの流れを解析する**ALE（Arbitrary Lagrangian-Eulerian）法** ★，気液混相流れを解析する**VOF（Volume of Fluid）法** ★などがあり，MAC系解法として各方面に発展していった．

### 2.2 SMAC法はどのような手順で計算する方法か

SMAC法（Simplified MAC法）の計算手順は以下の3段階で構成される。

**第1段階：仮速度の計算**

運動方程式から圧力項を除いた形で仮速度 $\tilde{\mathbf{u}}$ を求める。

$$
\frac{\tilde{\mathbf{u}} - \mathbf{u}^n}{\Delta t} = -(\mathbf{u}^n \cdot \nabla)\mathbf{u}^n + \frac{1}{\mathrm{Re}}\nabla^2 \mathbf{u}^n
$$

**第2段階：圧力補正値の計算**

仮速度の発散を打ち消すよう、圧力補正値 $\delta p$ に関するポアソン方程式を解く。

$$
\nabla^2 \delta p = \frac{1}{\Delta t}\nabla \cdot \tilde{\mathbf{u}}
$$

**第3段階：速度の補正**

圧力補正値を用いて速度を補正し、連続の式を満たす速度場 $\mathbf{u}^{n+1}$ を得る。

$$
\mathbf{u}^{n+1} = \tilde{\mathbf{u}} - \Delta t\,\nabla \delta p
$$

圧力も同様に $p^{n+1} = p^n + \delta p$ と更新する。

### 2.3 SMAC法とFractional Step法の違い

SMAC法とFractional Step法（分離解法）はいずれも非圧縮性流れの時間進行法であるが、以下の違いがある。

- **SMAC法**：仮速度計算で陽的に前時刻の速度を用い、その後に圧力補正を行う。時間精度は1次あるいは2次（アダムス・バッシュフォース法等を併用）。
- **Fractional Step法**：時間進行の分割（Fractional step）をより厳密に行い、移流項・粘性項・圧力項を独立した部分ステップで処理する。通常2次精度（例：移流項に2次精度Runge-Kutta、粘性項にCrank-Nicolson等）を達成できる。空間離散化はSMAC法と同一のスタガード格子上の差分近似を用いることが多い。

本質的には、両者は**時間進行の分割手順が異なるのみ**であり、空間離散化の方法は共通である。

---

## 問3 第8章「乱流の数値シミュレーション（RANS）」(25点, 内★5点)

### 3.1 乱流モデルとは何か

**乱流モデル**とは、レイノルズ平均を施したNavier-Stokes方程式（RANS方程式）に現れる未知の相関項である**レイノルズ応力** $-\rho\overline{u_i' u_j'}$ を、既知の平均流速やその勾配などの物理量で近似的に表現（モデル化）するための方法論である。

レイノルズ応力のモデル化には、一般に**渦粘性近似**（Boussinesq近似）

$$
-\rho\overline{u_i' u_j'} = \mu_t\left(\frac{\partial U_i}{\partial x_j} + \frac{\partial U_j}{\partial x_i}\right) - \frac{2}{3}\rho k\delta_{ij}
$$

が用いられる。ここで $\mu_t$ は渦粘性係数、$k$ は乱流エネルギーである。乱流モデルの核心はこの $\mu_t$ を如何に決定するかにある。

### 3.2 RANSとは何か

**RANS**（Reynolds-Averaged Navier-Stokes）とは、流れを平均成分と変動成分に分離するレイノルズ分解

$$
u_i(\mathbf{x}, t) = U_i(\mathbf{x}) + u_i'(\mathbf{x}, t), \quad p(\mathbf{x}, t) = P(\mathbf{x}) + p'(\mathbf{x}, t)
$$

をNavier-Stokes方程式に適用し、時間平均操作を施して得られる方程式系である：

$$
\frac{\partial U_i}{\partial x_i} = 0
$$

$$
\rho\frac{\partial U_i}{\partial t} + \rho U_j\frac{\partial U_i}{\partial x_j} = -\frac{\partial P}{\partial x_i} + \frac{\partial}{\partial x_j}\left(\mu\frac{\partial U_i}{\partial x_j} - \rho\overline{u_i' u_j'}\right)
$$

この方程式は**レイノルズ方程式**とも呼ばれる。RANSでは、時間スケールの大きい乱流変動はすべて統計的に平均化され、乱流の効果はレイノルズ応力項に集約される。工学的には定常計算が可能なため、広く産業応用されている。

### 3.3 RANSの種類

渦粘性モデルは、乱流の長さスケールや速度スケールの与え方により以下のように分類される。

| 分類 | 方程式数 | 代表モデル | 特徴 |
|------|----------|------------|------|
| **0方程式モデル** | 0 | 混合長モデル（Prandtl） | $\mu_t = \rho l_m^2 \|dU/dy\|$。$l_m$ を与えるだけで簡便だが、予め流れ場を知っている必要がある。 |
| **1方程式モデル** | 1 | $k$ モデル | 乱流エネルギー $k$ の輸送方程式を解き、$\mu_t = C_\mu \rho \sqrt{k}\,l$ とする。長さスケール $l$ は代数式で与える。 |
| **2方程式モデル** | 2 | $k$-$\varepsilon$ モデル | $k$ と散逸率 $\varepsilon$ の輸送方程式を解き、$\mu_t = C_\mu \rho k^2/\varepsilon$ とする。長さスケールまで輸送方程式で決定する。最も実用的。 |
| **応力方程式モデル** | 6+ | レイノルズ応力モデル（RSM） | 渦粘性近似を用いず、レイノルズ応力の輸送方程式を直接解く。高精度だが計算コスト大。 |

### ★ 3.4 低レイノルズ数型 $k$-$\varepsilon$ モデル

標準 $k$-$\varepsilon$ モデルは高レイノルズ数乱流を前提としており、壁法則を用いて壁面近傍の処理を行うため、壁面まで直接積分することができない。**低レイノルズ数型 $k$-$\varepsilon$ モデル**は、壁面の粘性底層まで積分可能にするため、以下の修正を施したモデルである。

- **減衰関数（ダンピング関数）$f_\mu$, $f_1$, $f_2$** を導入し、壁面近傍での乱流粘性の低減を表現する：

$$
\mu_t = C_\mu f_\mu \rho \frac{k^2}{\varepsilon}
$$

- $k$ 方程式および $\varepsilon$ 方程式のモデル定数 $C_{\varepsilon 1}$, $C_{\varepsilon 2}$ にも減衰関数 $f_1$, $f_2$ を乗じる。

- 代表的なモデルとして、**Launder-Sharmaモデル**、**Nagano-Tagawaモデル**、**Abe-Kondoh-Nagano (AKN) モデル**などがある。

低レイノルズ数型では、第1格子点を壁面の粘性底層内（$y^+ \sim 1$）に配置する必要があり、壁垂直方向の解像度が高く要求される。

---

## 問4 第9章「乱流の数値シミュレーション（LES）」(25点, 内★5点)

### 4.1 LESとは何か

**LES**（Large-Eddy Simulation）とは、乱流場に対して空間フィルター操作を施し、計算格子幅より大きいスケールの渦（GS: Grid-Scale成分）を直接数値計算し、格子幅より小さいスケールの渦（SGS: Sub-Grid Scale成分）の効果のみをモデル化する手法である。

空間フィルター操作は、フィルター関数 $G$ を用いて

$$
\overline{u}_i(\mathbf{x}, t) = \int G(\mathbf{x} - \mathbf{x}') u_i(\mathbf{x}', t) \,d\mathbf{x}'
$$
と定義される。フィルターを施したNS方程式には、SGS応力

$$
\tau_{ij}^{\mathrm{SGS}} = \overline{u_i u_j} - \overline{u}_i\overline{u}_j
$$
が現れ、これをモデル化する必要がある。

RANSと異なり、LESでは乱流エネルギーの大部分を担う大規模渦を直接計算するため、流れの非定常性や大規模構造の時間発展を高精度に捉えることができる。DNSより計算負荷が低く、RANSより高精度という位置づけである。

### 4.2 LESの種類

SGS応力のモデル化手法により、以下の2つが代表的である。

**Smagorinskyモデル**

渦粘性型の最も基本的なSGSモデルである。

$$
\tau_{ij}^{\mathrm{SGS}} - \frac{1}{3}\tau_{kk}^{\mathrm{SGS}}\delta_{ij} = -2\nu_{\mathrm{SGS}}\overline{S}_{ij}
$$
$$
\nu_{\mathrm{SGS}} = (C_S \overline{\Delta})^2 |\overline{S}|, \quad |\overline{S}| = \sqrt{2\overline{S}_{ij}\overline{S}_{ij}}
$$
ここで $C_S$ はSmagorinsky定数（通常 $C_S \approx 0.1 \sim 0.2$）、$\overline{\Delta}$ はフィルター幅（格子幅）である。簡便であるが、層流せん断流でも渦粘性が非零となる欠点がある。

**ダイナミックモデル ★**

後述（4.4節）。

### 4.3 RANSとLESの違い

| 項目 | RANS | LES |
|------|------|------|
| **平均操作** | 時間平均（レイノルズ平均） | 空間フィルター |
| **計算対象** | 全スケールの乱流をモデル化 | GS成分を直接計算、SGS成分のみモデル化 |
| **計算結果** | 時間平均場（定常計算が主） | 非定常流れ場（時間発展） |
| **計算コスト** | 低〜中 | 中〜高（RANSの10〜100倍） |
| **精度** | 複雑流れでは限界あり | 剥離流れ等でRANSより高精度 |
| **格子解像度** | 壁面近傍以外では比較的粗い格子で可 | 乱流エネルギーの約80%を解像する必要あり |

本質的な差異は、RANSが**全乱流変動**を統計的に平均化しモデル化するのに対し、LESは**空間フィルター**により大規模構造（GS成分）を陽に計算し、小スケール（SGS成分）のみをモデル化する点にある。

### ★ 4.4 ダイナミックモデル

**ダイナミックモデル**（Germanoら, 1991）は、Smagorinskyモデルのモデル定数 $C_S$ を経験的に与えるのではなく、**流れ場から動的に（局所的・瞬時的に）決定する手法**である。

原理は以下の通りである。2種類のフィルター幅 $\overline{\Delta}$（グリッドフィルター）と $\widetilde{\Delta}$（テストフィルター、通常 $\widetilde{\Delta} = 2\overline{\Delta}$）を用い、それぞれのスケールで成立するGermanoの恒等式

$$
L_{ij} = T_{ij} - \widetilde{\tau_{ij}^{\mathrm{SGS}}}, \quad L_{ij} = \widetilde{\overline{u}_i\overline{u}_j} - \widetilde{\overline{u}}_i\widetilde{\overline{u}}_j
$$
に基づき、最小二乗法（Lillyの方法）により

$$
C_S^2 = -\frac{\langle L_{ij} M_{ij} \rangle}{2\langle M_{ij} M_{ij} \rangle}, \quad M_{ij} = \widetilde{\Delta}^2|\widetilde{\overline{S}}|\widetilde{\overline{S}}_{ij} - \overline{\Delta}^2\widetilde{|\overline{S}|\overline{S}_{ij}}
$$
として $C_S$ を決定する。$\langle\cdot\rangle$ は空間平均（あるいはアンサンブル平均）を表す。

ダイナミックモデルにより、壁面近傍で自動的に $C_S \to 0$ となる（層流化）、層流から乱流への遷移が自動的に捉えられるなど、Smagorinskyモデルの欠点が大幅に改善される。

---

## 参考文献

1. 数値流体力学（教科書）第4章・第5章・第8章・第9章
2. Harlow, F.H. and Welch, J.E., "Numerical Calculation of Time-Dependent Viscous Incompressible Flow of Fluid with Free Surface", Phys. Fluids, Vol.8, pp.2182-2189, 1965.
3. Germano, M., Piomelli, U., Moin, P. and Cabot, W.H., "A dynamic subgrid-scale eddy viscosity model", Phys. Fluids A, Vol.3, pp.1760-1765, 1991.
4. Launder, B.E. and Sharma, B.I., "Application of the Energy-Dissipation Model of Turbulence to the Calculation of Flow Near a Spinning Disc", Lett. Heat Mass Transfer, Vol.1, pp.131-138, 1974.
5. Smagorinsky, J., "General Circulation Experiments with the Primitive Equations", Mon. Weather Rev., Vol.91, pp.99-164, 1963.
