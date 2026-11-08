// ============================================================================
//  SMSATBOX · eUICC / eSIM 适配模块
//  ---------------------------------------------------------------------------
//  支持淘宝「小白卡」这类可编程 eUICC 实体卡（9eSIM / 5ber / eSIM.me 同技术）。
//
//  实现方式：SGP.22 ES10 系列 APDU，通过模组的标准逻辑通道指令与卡片通信：
//    AT+CCHO="<AID>"             打开逻辑通道，返回 channel
//    AT+CGLA=<ch>,<len>,"<hex>"  传输 APDU
//    AT+CCHC=<ch>                关闭逻辑通道
//
//  ES10 命令（对照 lpac v2.3.0 euicc/es10c.c）：
//    BF3E 035C015A              GetEuiccInfo（取 EID）
//    BF22 00                    GetEuiccConfiguredAddresses / 内存信息
//    BF2D 085C065A9F70909192    GetProfilesInfo（列 profile）
//    BF31 + A0{5A iccid}+8101FF EnableProfile
//    BF32 + A0{5A iccid}+8101FF DisableProfile
//    BF33 + 5A iccid            DeleteProfile
//    BF29 + 5A iccid + 90 name  SetNickname
//
//  设计原则：
//    - 不侵入原有短信/来电业务，独立模块
//    - 自动检测：开机时探测 ISD-R AID，存在才启用功能
//    - 失败可降级：非 eUICC 卡不报错，只是功能不可用
// ============================================================================
#pragma once

#include <Arduino.h>
#include <vector>

// ---------------------------------------------------------------------------
// 数据结构
// ---------------------------------------------------------------------------
struct EuiccProfile {
    String iccid;      // 完整 ICCID（19/20 位）
    int state = 0;     // 0=disabled, 1=enabled
    String nickname;   // 用户自定义名称
    String provider;   // 运营商名（profileName）
    String name;       // profile 名称
    bool malformed = false;  // 解析异常标记

    bool enabled() const { return state == 1; }
};

struct EuiccInfo {
    String eid;              // 32 位十六进制 EID
    bool valid = false;
    int installedApps = 0;   // 已安装应用数
    long freeNonVolatile = -1;  // 非易失剩余（KB 或字节，视卡而定）
    long freeVolatile = -1;
};

// ---------------------------------------------------------------------------
// eUICC 管理器
// ---------------------------------------------------------------------------
class Euicc {
public:
    /** 绑定到某个卡槽（1 或 2），必须在 begin 前调用 */
    void bindSlot(int slotIndex);

    /**
     * 探测该卡槽的卡是否为 eUICC。
     * 原理：尝试打开 ISD-R AID 的逻辑通道，成功即为 eUICC。
     * 会缓存结果，probe() 只在开机/换卡时调用。
     */
    bool probe(bool force = false);

    /** 是否已确认是 eUICC 卡（probe 成功后为 true） */
    bool isEuicc() const { return isEuicc_; }

    /** 是否已经探测过（无论结果） */
    bool probed() const { return probed_; }

    /** 用户是否启用了 eSIM 管理功能（手动开关） */
    void setEnabled(bool on) { userEnabled_ = on; }
    bool userEnabled() const { return userEnabled_; }

    /** 功能是否真正可用 = 是 eUICC 卡 && 用户已启用 */
    bool available() const { return isEuicc_ && userEnabled_; }

    // ---- ES10 操作 ----
    /** 读取 EID 与卡片容量信息 */
    bool readInfo(EuiccInfo* out);

    /** 列出所有 profile */
    bool listProfiles(std::vector<EuiccProfile>* out);

    /** 启用指定 ICCID 的 profile（会触发 REFRESH，可能需要重启模组） */
    bool enableProfile(const String& iccid);

    /** 禁用指定 ICCID 的 profile */
    bool disableProfile(const String& iccid);

    /** 删除指定 ICCID 的 profile（必须先禁用） */
    bool deleteProfile(const String& iccid);

    /** 修改 profile 的显示名称/标签 */
    bool setNickname(const String& iccid, const String& nickname);

    /** 最近一次错误信息 */
    const String& lastError() const { return lastError_; }

    // ---- 状态缓存（供上报用，避免频繁访问卡片）----
    const EuiccInfo& cachedInfo() const { return info_; }
    const std::vector<EuiccProfile>& cachedProfiles() const { return profiles_; }
    uint32_t lastRefreshMs() const { return lastRefreshMs_; }

    /** 刷新并缓存 info + profiles（低频调用，例如每 5 分钟） */
    bool refresh();

private:
    int slot_ = 1;
    bool probed_ = false;
    bool isEuicc_ = false;
    bool userEnabled_ = true;   // 默认自动启用（探测到 eUICC 就打开）

    EuiccInfo info_;
    std::vector<EuiccProfile> profiles_;
    uint32_t lastRefreshMs_ = 0;
    String lastError_;

    // ---- 底层 APDU 通道 ----
    bool openChannel(const String& aid, int* channel);
    bool closeChannel(int channel);
    bool transmit(int channel, const String& apduHex, String* respHex);

    /** 发送一条 AT 指令并等待期望响应（用对应卡槽的串口） */
    bool atCommand(const String& cmd, const String& expect, uint32_t timeoutMs,
                   String* response);

    /** ES10 请求-响应（自动分片大响应） */
    bool es10Exchange(int channel, const String& bodyHex, String* outHex);

    void setError(const String& msg);
};
