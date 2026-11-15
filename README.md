# OrangeFox Recovery — OPPO Reno12 (PJV110 / mt6895)

为 **OPPO Reno12 国行（PJV110 / PLJ110，天玑 8250 / MT6896）** 从零移植 OrangeFox Recovery
的构建仓库。设备状态：ColorOS 17（Android 17 用户空间、GKI 6.12 内核）、A/B 双槽、
动态分区、**没有独立 recovery 分区**。

> ⚠️ 本仓库产物是 **vendor_boot 镜像**，不是 recovery 分区镜像。
> 刷机命令是 `fastboot flash vendor_boot_a`，刷错分区会有变砖风险。

## 目录结构

```
device/oplus/PJV110/          设备树
  BoardConfig.mk              板级配置（分区尺寸、A/B、OrangeFox 变量）
  device.mk / twrp_PJV110.mk  产品定义
  AndroidProducts.mk          lunch 入口（twrp_PJV110-eng）
  recovery.fstab              TWRP fstab（含 ColorOS 动态分区）
  vendorsetup.sh              OF_* / FOX_* 变量
  prebuilt/kernel             从原厂 boot_a.img 提取的 GKI 内核（19MB）
prebuilt/
  dtb.bin                     原厂 vendor_boot dtb（327KB）
  modules.tar.gz              原厂 vendor_boot 内的 235 个 .ko（39MB → 9MB）
  modules-meta.tar.gz         modules.load.recovery / modules.dep 等
  firmware.tar.gz             原厂 /vendor/firmware（34 个文件）
  vendor_boot.json            原厂 vendor_boot 头参数
scripts/pack.sh               编译后：取 ramdisk → 注入模块 → 重打 vendor_boot
tools/                        androidimg / cpio_tool / mkvendor_boot / gen_init_rc
.github/workflows/build.yml   GitHub Actions 构建流程
```

## 使用方法

> 因为 GitHub 网页上传单文件上限 25MB，内核（18.5MB）单独上传，其余内容在一个 zip 里。

1. 在 GitHub 新建一个**空仓库**（Public / Private 均可），不要勾选 README。
2. 解压 `OrangeFox-PJV110-repo.zip`，把里面的**全部内容**（包括 `.github` 目录）
   上传到仓库根目录。
   - 网页上传：`Add file → Upload files`，把 `device`、`prebuilt`、`scripts`、`tools`、
     `.github`、`README.md` 一起拖进去。
   - 注意 `.github` 是隐藏目录：如果拖拽没带上，用 `Add file → Create new file`，
     文件名输入 `.github/workflows/build.yml`，把本地文件内容粘进去。
3. 单独上传内核文件：仓库里进入 `device/oplus/PJV110/prebuilt/` →
   `Add file → Upload files` → 选择 `kernel` 文件（18.5MB）。
   上传后确认路径是 `device/oplus/PJV110/prebuilt/kernel`。
4. 打开仓库的 **Actions** 页面 → 左侧 `orangeFox-PJV110` → `Run workflow`。
5. 等待 30–90 分钟（源码同步约 25–40GB，首次较慢；构建约 20–40 分钟）。
6. 构建成功后，在该次运行页面底部 **Artifacts** 下载
   `OrangeFox-PJV110-vendor_boot`，里面是：
   - `OrangeFox-PJV110-vendor_boot.img`  ← 要刷的镜像
   - `build.log`                          ← 编译日志

## 刷入（确认已解锁 BL、已备份）

```bash
adb reboot bootloader
fastboot devices
fastboot flash vendor_boot_a OrangeFox-PJV110-vendor_boot.img
fastboot reboot recovery
```

如果开机后进不去系统（正常开机被破坏），先刷回原厂 vendor_boot：

```bash
fastboot flash vendor_boot_a vendor_boot_a_stock.img
fastboot reboot
```

（原厂镜像就是你之前 dd 出来的 `vendor_boot_a.img`，请务必保留备份。）

## 已知限制

- **不能解密 /data**：系统使用 f2fs + 元数据加密 + Trustonic keymaster，当前版本
  `TW_INCLUDE_CRYPTO := false`。进入 rec 后 /data 会提示无法解密，取消即可。
- **首次构建大概率需要调整**：设备树是按 AOSP/OrangeFox 通用规范手写的，第一次 CI
  很可能在 `lunch` 或 soong 阶段报错；把 `build.log` 发回来按错误改。
- 本设备系统是**移植包**（系统指纹 `alps/sys_mssi_64_cn_armv82`，机型 PLJ110），
  vendor_boot 取自该 ROM；换 ROM 后需要重新导出 vendor_boot 并更新 `prebuilt/`。

## 产物原理

```
mka recoveryimage  →  recovery.img（内核+橙狐 ramdisk）
                        │
        tools/androidimg.py unpack  →  ramdisk.cpio
        tools/cpio_tool.py extract  →  ramdisk 目录
        注入 prebuilt/modules.tar.gz + firmware.tar.gz + 生成的 init.recovery.mt6895.rc
        tools/cpio_tool.py pack     →  新 ramdisk.cpio
        tools/mkvendor_boot.py build →  vendor_boot.img（原厂 dtb/cmdline，lz4 压缩）
```

原厂 vendor_boot 的往返验证结果：849 个 cpio 条目、dtb、cmdline 全部一致，
重压缩后 45.1MB（原厂 48.4MB），镜像 45.5MB < 64MB 分区上限。
