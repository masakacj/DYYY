#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface KwaiParseHUD : NSObject

+ (instancetype)shared;
- (void)showStatus:(NSString *)status progress:(float)progress;
- (void)showMessage:(NSString *)message;
- (void)dismiss;

@end

NS_ASSUME_NONNULL_END
