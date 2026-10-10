#import "KwaiParseHUD.h"

@interface KwaiParseHUD ()
@property(nonatomic, strong) UIView *container;
@property(nonatomic, strong) UILabel *label;
@property(nonatomic, strong) UIProgressView *progressView;
@property(nonatomic, strong) UIActivityIndicatorView *spinner;
@end

@implementation KwaiParseHUD

+ (instancetype)shared {
    static KwaiParseHUD *hud;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
      hud = [[self alloc] init];
    });
    return hud;
}

- (UIWindow *)targetWindow {
    UIApplication *app = UIApplication.sharedApplication;
    for (UIScene *scene in app.connectedScenes) {
        if (![scene isKindOfClass:[UIWindowScene class]]) continue;
        UIWindowScene *windowScene = (UIWindowScene *)scene;
        if (windowScene.activationState != UISceneActivationStateForegroundActive) continue;
        for (UIWindow *window in windowScene.windows) {
            if (window.isKeyWindow) return window;
        }
        for (UIWindow *window in windowScene.windows) {
            if (!window.hidden && window.alpha > 0.01) return window;
        }
    }
    return nil;
}

- (void)ensureViews {
    UIWindow *window = [self targetWindow];
    if (!window) return;

    if (!self.container) {
        UIView *container = [[UIView alloc] initWithFrame:CGRectZero];
        container.backgroundColor = [UIColor colorWithWhite:0.08 alpha:0.90];
        container.layer.cornerRadius = 14.0;
        container.layer.masksToBounds = YES;
        container.userInteractionEnabled = NO;

        UILabel *label = [[UILabel alloc] initWithFrame:CGRectZero];
        label.textColor = UIColor.whiteColor;
        label.font = [UIFont systemFontOfSize:14.0 weight:UIFontWeightMedium];
        label.textAlignment = NSTextAlignmentCenter;
        label.numberOfLines = 2;

        UIProgressView *progress = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
        progress.progressTintColor = UIColor.whiteColor;
        progress.trackTintColor = [UIColor colorWithWhite:1.0 alpha:0.20];

        UIActivityIndicatorView *spinner =
            [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
        spinner.color = UIColor.whiteColor;
        [spinner startAnimating];

        [container addSubview:label];
        [container addSubview:progress];
        [container addSubview:spinner];
        self.container = container;
        self.label = label;
        self.progressView = progress;
        self.spinner = spinner;
    }

    if (self.container.superview != window) {
        [self.container removeFromSuperview];
        [window addSubview:self.container];
    }

    CGFloat width = MIN(300.0, CGRectGetWidth(window.bounds) - 36.0);
    CGFloat height = 86.0;
    self.container.frame = CGRectMake((CGRectGetWidth(window.bounds) - width) / 2.0,
                                      CGRectGetHeight(window.bounds) * 0.18,
                                      width,
                                      height);
    self.spinner.frame = CGRectMake(16.0, 18.0, 24.0, 24.0);
    self.label.frame = CGRectMake(48.0, 12.0, width - 64.0, 38.0);
    self.progressView.frame = CGRectMake(20.0, 64.0, width - 40.0, 4.0);
}

- (void)showStatus:(NSString *)status progress:(float)progress {
    dispatch_async(dispatch_get_main_queue(), ^{
      [self ensureViews];
      self.container.hidden = NO;
      self.container.alpha = 1.0;
      self.label.text = status ?: @"处理中…";

      if (progress >= 0.0f) {
          self.spinner.hidden = YES;
          self.progressView.hidden = NO;
          self.progressView.progress = MAX(0.0f, MIN(1.0f, progress));
      } else {
          self.spinner.hidden = NO;
          self.progressView.hidden = YES;
          [self.spinner startAnimating];
      }
    });
}

- (void)showMessage:(NSString *)message {
    [self showStatus:message progress:-1.0f];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.6 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      [self dismiss];
    });
}

- (void)dismiss {
    dispatch_async(dispatch_get_main_queue(), ^{
      if (!self.container || self.container.hidden) return;
      [UIView animateWithDuration:0.18
          animations:^{
            self.container.alpha = 0.0;
          }
          completion:^(__unused BOOL finished) {
            self.container.hidden = YES;
            self.container.alpha = 1.0;
          }];
    });
}

@end
