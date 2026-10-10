#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface KwaiParseManager : NSObject

+ (instancetype)shared;

// 被快手复制链接动作写入剪贴板时，仅缓存当前作品候选，不自动触发解析。
- (void)handleCandidateText:(nullable NSString *)text;
- (void)handleCandidateItems:(nullable NSArray *)items;

// 给快手页面安装长按入口；真正弹窗前会再判断是否像视频播放页。
- (void)attachLongPressToController:(UIViewController *)controller;
- (void)showLoadedHint;

@end

NS_ASSUME_NONNULL_END
