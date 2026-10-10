#import "KwaiParseManager.h"
#import "KwaiParseHUD.h"

#import <Photos/Photos.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

static NSString *const kKwaiParseInterfaceKey = @"KwaiParseInterfaceURL";
static NSString *const kKwaiParseEnabledKey = @"KwaiParseEnabled";
static const void *kKwaiParseLongPressKey = &kKwaiParseLongPressKey;

@interface KwaiParseManager () <NSURLSessionDownloadDelegate, UIGestureRecognizerDelegate>
@property(nonatomic, copy) NSString *lastCandidate;
@property(nonatomic, strong) NSDate *lastCandidateDate;
@property(nonatomic, assign) BOOL resolving;
@property(nonatomic, strong) NSURLSession *downloadSession;
@property(nonatomic, strong) NSURLSessionDownloadTask *downloadTask;
@property(nonatomic, copy) NSString *downloadFileStem;
@property(nonatomic, assign) BOOL downloadFileHandled;
@end

@implementation KwaiParseManager

+ (instancetype)shared {
    static KwaiParseManager *manager;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
      manager = [[self alloc] init];
    });
    return manager;
}

#pragma mark - Entry

- (BOOL)isEnabled {
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    if ([defaults objectForKey:kKwaiParseEnabledKey] == nil) return YES;
    return [defaults boolForKey:kKwaiParseEnabledKey];
}

- (void)showLoadedHint {
    if (![self isEnabled]) return;
    [[KwaiParseHUD shared] showMessage:@"KwaiParse 已加载\n长按视频播放页打开接口菜单"];
}

- (void)handleCandidateItems:(NSArray *)items {
    if (![items isKindOfClass:[NSArray class]]) return;
    for (id item in items) {
        if ([item isKindOfClass:[NSString class]]) {
            [self handleCandidateText:item];
            continue;
        }
        if (![item isKindOfClass:[NSDictionary class]]) continue;
        for (id value in [(NSDictionary *)item allValues]) {
            if ([value isKindOfClass:[NSString class]]) {
                [self handleCandidateText:value];
            } else if ([value isKindOfClass:[NSURL class]]) {
                [self handleCandidateText:[(NSURL *)value absoluteString]];
            }
        }
    }
}

- (void)handleCandidateText:(NSString *)text {
    if (![self isEnabled] || text.length == 0) return;

    NSString *candidate = [self extractCandidate:text];
    if (candidate.length == 0) return;

    @synchronized(self) {
        self.lastCandidate = candidate;
        self.lastCandidateDate = [NSDate date];
    }
}


#pragma mark - Long-press entry

- (void)attachLongPressToController:(UIViewController *)controller {
    if (![self isEnabled] || !controller || !controller.view) return;
    if ([controller isKindOfClass:[UIAlertController class]]
        || [controller isKindOfClass:[UINavigationController class]]
        || [controller isKindOfClass:[UITabBarController class]]) {
        return;
    }

    NSString *className = NSStringFromClass(controller.class);
    if ([className hasPrefix:@"UI"]
        || [className hasPrefix:@"_UI"]
        || [className hasPrefix:@"MF"]
        || [className hasPrefix:@"PHPicker"]) {
        return;
    }

    if (objc_getAssociatedObject(controller.view, kKwaiParseLongPressKey)) return;

    UILongPressGestureRecognizer *gesture =
        [[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(handleVideoPageLongPress:)];
    gesture.minimumPressDuration = 0.65;
    gesture.cancelsTouchesInView = NO;
    gesture.delaysTouchesBegan = NO;
    gesture.delaysTouchesEnded = NO;
    gesture.delegate = self;
    [controller.view addGestureRecognizer:gesture];
    objc_setAssociatedObject(controller.view,
                             kKwaiParseLongPressKey,
                             gesture,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer
        shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)otherGestureRecognizer {
    return YES;
}

- (UIViewController *)owningViewControllerForView:(UIView *)view {
    UIResponder *responder = view;
    while (responder) {
        if ([responder isKindOfClass:[UIViewController class]]) {
            return (UIViewController *)responder;
        }
        responder = responder.nextResponder;
    }
    return [self topController];
}

- (BOOL)viewTreeLooksLikeVideo:(UIView *)view depth:(NSUInteger)depth budget:(NSInteger *)budget {
    if (!view || depth > 6 || !budget || *budget <= 0) return NO;
    (*budget)--;

    NSString *name = NSStringFromClass(view.class).lowercaseString;
    NSArray<NSString *> *tokens = @[
        @"video", @"player", @"photo", @"feed", @"render", @"surface", @"playback", @"slide"
    ];
    for (NSString *token in tokens) {
        if ([name containsString:token]) return YES;
    }

    for (UIView *subview in view.subviews) {
        if ([self viewTreeLooksLikeVideo:subview depth:depth + 1 budget:budget]) return YES;
    }
    return NO;
}

- (BOOL)controllerLooksLikeVideoPage:(UIViewController *)controller {
    NSString *name = NSStringFromClass(controller.class).lowercaseString;

    NSArray<NSString *> *negative = @[
        @"setting", @"login", @"search", @"comment", @"message", @"profile",
        @"camera", @"record", @"editor", @"album", @"web", @"shop"
    ];
    for (NSString *token in negative) {
        if ([name containsString:token]) return NO;
    }

    NSArray<NSString *> *positive = @[
        @"photo", @"detail", @"feed", @"video", @"player", @"play",
        @"slide", @"work", @"pager", @"content"
    ];
    for (NSString *token in positive) {
        if ([name containsString:token]) return YES;
    }

    NSInteger budget = 180;
    return [self viewTreeLooksLikeVideo:controller.view depth:0 budget:&budget];
}

- (NSString *)candidateFromObject:(id)object
                            depth:(NSUInteger)depth
                          visited:(NSMutableSet<NSValue *> *)visited
                           budget:(NSInteger *)budget {
    if (!object || depth > 4 || !budget || *budget <= 0) return nil;
    (*budget)--;

    if ([object isKindOfClass:[NSString class]]) {
        return [self extractCandidate:(NSString *)object];
    }
    if ([object isKindOfClass:[NSURL class]]) {
        return [self extractCandidate:[(NSURL *)object absoluteString]];
    }
    if ([object isKindOfClass:[NSNumber class]]
        || [object isKindOfClass:[NSData class]]
        || [object isKindOfClass:[NSDate class]]) {
        return nil;
    }

    NSValue *pointer = [NSValue valueWithPointer:(__bridge const void *)object];
    if ([visited containsObject:pointer]) return nil;
    [visited addObject:pointer];

    if ([object isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dictionary = (NSDictionary *)object;
        for (id key in dictionary) {
            NSString *candidate = [self candidateFromObject:key
                                                       depth:depth + 1
                                                     visited:visited
                                                      budget:budget];
            if (candidate.length > 0) return candidate;

            candidate = [self candidateFromObject:dictionary[key]
                                             depth:depth + 1
                                           visited:visited
                                            budget:budget];
            if (candidate.length > 0) return candidate;
        }
        return nil;
    }

    if ([object isKindOfClass:[NSArray class]]
        || [object isKindOfClass:[NSSet class]]
        || [object isKindOfClass:[NSOrderedSet class]]) {
        for (id value in object) {
            NSString *candidate = [self candidateFromObject:value
                                                       depth:depth + 1
                                                     visited:visited
                                                      budget:budget];
            if (candidate.length > 0) return candidate;
        }
        return nil;
    }

    if ([object isKindOfClass:[UIView class]]
        || [object isKindOfClass:[CALayer class]]
        || [object isKindOfClass:[UIGestureRecognizer class]]) {
        return nil;
    }

    Class cls = object_getClass(object);
    NSUInteger classDepth = 0;
    while (cls && cls != [NSObject class] && classDepth < 5 && *budget > 0) {
        unsigned int count = 0;
        Ivar *ivars = class_copyIvarList(cls, &count);
        for (unsigned int i = 0; i < count && *budget > 0; i++) {
            const char *type = ivar_getTypeEncoding(ivars[i]);
            if (!type || type[0] != '@') continue;

            id value = nil;
            @try {
                value = object_getIvar(object, ivars[i]);
            } @catch (__unused NSException *exception) {
                value = nil;
            }
            if (!value) continue;

            NSString *candidate = [self candidateFromObject:value
                                                       depth:depth + 1
                                                     visited:visited
                                                      budget:budget];
            if (candidate.length > 0) {
                free(ivars);
                return candidate;
            }
        }
        free(ivars);
        cls = class_getSuperclass(cls);
        classDepth++;
    }
    return nil;
}

- (NSString *)currentCandidateForController:(UIViewController *)controller {
    NSInteger budget = 520;
    NSMutableSet<NSValue *> *visited = [NSMutableSet set];
    NSString *candidate = [self candidateFromObject:controller
                                               depth:0
                                             visited:visited
                                              budget:&budget];
    if (candidate.length > 0) return candidate;

    @synchronized(self) {
        if (self.lastCandidate.length > 0
            && self.lastCandidateDate
            && [[NSDate date] timeIntervalSinceDate:self.lastCandidateDate] <= 45.0) {
            return self.lastCandidate;
        }
    }
    return nil;
}

- (void)handleVideoPageLongPress:(UILongPressGestureRecognizer *)gesture {
    if (gesture.state != UIGestureRecognizerStateBegan || ![self isEnabled]) return;

    UIViewController *controller = [self owningViewControllerForView:gesture.view];
    if (!controller) return;

    NSString *candidate = [self currentCandidateForController:controller];
    if (![self controllerLooksLikeVideoPage:controller] && candidate.length == 0) {
        return;
    }

    [self presentLongPressMenuFromController:controller candidate:candidate];
}

- (void)presentLongPressMenuFromController:(UIViewController *)controller candidate:(NSString *)candidate {
    if (!controller || controller.presentedViewController) return;

    BOOL configured = [self interfaceBase].length > 0;
    NSString *message = configured ? @"选择操作" : @"尚未设置解析接口地址";

    UIAlertController *sheet =
        [UIAlertController alertControllerWithTitle:@"快手接口工具"
                                            message:message
                                     preferredStyle:UIAlertControllerStyleActionSheet];

    [sheet addAction:[UIAlertAction actionWithTitle:@"接口解析"
                                             style:UIAlertActionStyleDefault
                                           handler:^(__unused UIAlertAction *action) {
      if ([self interfaceBase].length == 0) {
          [self presentInterfaceSettings];
          return;
      }

      NSString *current = candidate.length > 0 ? candidate : [self currentCandidateForController:controller];
      if (current.length == 0) {
          [[KwaiParseHUD shared] showMessage:@"未识别到当前视频\n可先点一次分享→复制链接后再长按"];
          return;
      }
      [self resolveCandidate:current];
    }]];

    [sheet addAction:[UIAlertAction actionWithTitle:@"设置"
                                             style:UIAlertActionStyleDefault
                                           handler:^(__unused UIAlertAction *action) {
      [self presentInterfaceSettings];
    }]];

    [sheet addAction:[UIAlertAction actionWithTitle:@"取消"
                                             style:UIAlertActionStyleCancel
                                           handler:nil]];

    UIPopoverPresentationController *popover = sheet.popoverPresentationController;
    if (popover) {
        popover.sourceView = controller.view;
        popover.sourceRect = CGRectMake(CGRectGetMidX(controller.view.bounds),
                                        CGRectGetMidY(controller.view.bounds),
                                        1.0,
                                        1.0);
        popover.permittedArrowDirections = 0;
    }

    [controller presentViewController:sheet animated:YES completion:nil];
}

#pragma mark - Candidate parsing

- (NSString *)extractCandidate:(NSString *)text {
    NSError *error = nil;
    NSRegularExpression *photoRegex =
        [NSRegularExpression regularExpressionWithPattern:@"(?i)(3x[a-z0-9]{10,20})"
                                                  options:0
                                                    error:&error];
    NSTextCheckingResult *photoMatch =
        [photoRegex firstMatchInString:text options:0 range:NSMakeRange(0, text.length)];
    if (photoMatch.numberOfRanges > 1) {
        return [text substringWithRange:[photoMatch rangeAtIndex:1]];
    }

    NSRegularExpression *urlRegex =
        [NSRegularExpression regularExpressionWithPattern:@"https?://[^\\s]+"
                                                  options:NSRegularExpressionCaseInsensitive
                                                    error:&error];
    NSArray<NSTextCheckingResult *> *matches =
        [urlRegex matchesInString:text options:0 range:NSMakeRange(0, text.length)];

    NSCharacterSet *trimSet =
        [NSCharacterSet characterSetWithCharactersInString:@"，。！？、；：）》】」』”’'\"),.;:!?]}"];

    for (NSTextCheckingResult *match in matches) {
        NSString *raw = [text substringWithRange:match.range];
        while (raw.length > 0 && [trimSet characterIsMember:[raw characterAtIndex:raw.length - 1]]) {
            raw = [raw substringToIndex:raw.length - 1];
        }

        NSURL *url = [NSURL URLWithString:raw];
        NSString *host = url.host.lowercaseString;
        if ([self isAllowedKuaishouHost:host]) return raw;
    }

    return nil;
}

- (BOOL)isAllowedKuaishouHost:(NSString *)host {
    if (host.length == 0) return NO;
    NSArray<NSString *> *domains = @[
        @"kuaishou.com",
        @"gifshow.com",
        @"chenzhongtech.com",
        @"ksurl.cn",
        @"kwai.com"
    ];
    for (NSString *domain in domains) {
        if ([host isEqualToString:domain] || [host hasSuffix:[@"." stringByAppendingString:domain]]) {
            return YES;
        }
    }
    return NO;
}

#pragma mark - Resolver

- (NSString *)interfaceBase {
    NSString *value = [NSUserDefaults.standardUserDefaults stringForKey:kKwaiParseInterfaceKey];
    return [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
}

- (NSURL *)resolverURLForCandidate:(NSString *)candidate {
    NSString *base = [self interfaceBase];
    if (base.length == 0) return nil;

    NSMutableCharacterSet *allowed = [NSMutableCharacterSet alphanumericCharacterSet];
    [allowed addCharactersInString:@"-._~"];
    NSString *encoded = [candidate stringByAddingPercentEncodingWithAllowedCharacters:allowed];
    if (encoded.length == 0) return nil;

    NSString *urlString;
    if ([base containsString:@"%@"]) {
        urlString = [NSString stringWithFormat:base, encoded];
    } else {
        urlString = [base stringByAppendingString:encoded];
    }
    return [NSURL URLWithString:urlString];
}

- (void)resolveCandidate:(NSString *)candidate {
    @synchronized(self) {
        if (self.resolving) return;
        self.resolving = YES;
    }

    NSURL *url = [self resolverURLForCandidate:candidate];
    if (!url) {
        self.resolving = NO;
        [[KwaiParseHUD shared] showMessage:@"解析接口地址无效"];
        return;
    }

    [[KwaiParseHUD shared] showStatus:@"正在解析快手视频…" progress:-1.0f];

    NSMutableURLRequest *request =
        [NSMutableURLRequest requestWithURL:url
                               cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                           timeoutInterval:22.0];
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"no-cache" forHTTPHeaderField:@"Cache-Control"];

    NSURLSessionDataTask *task =
        [NSURLSession.sharedSession dataTaskWithRequest:request
                                     completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
      @synchronized(self) {
          self.resolving = NO;
      }

      if (error || data.length == 0) {
          [[KwaiParseHUD shared] dismiss];
          [self presentError:error.localizedDescription ?: @"解析接口无响应"];
          return;
      }

      NSError *jsonError = nil;
      id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
      if (![object isKindOfClass:[NSDictionary class]]) {
          [[KwaiParseHUD shared] dismiss];
          [self presentError:jsonError.localizedDescription ?: @"接口返回格式错误"];
          return;
      }

      NSDictionary *json = (NSDictionary *)object;
      NSInteger code = [json[@"code"] integerValue];
      if (code != 0 && code != 200) {
          [[KwaiParseHUD shared] dismiss];
          [self presentError:[json[@"msg"] isKindOfClass:[NSString class]] ? json[@"msg"] : @"接口返回错误"];
          return;
      }

      NSDictionary *payload = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : nil;
      NSArray *videoList = [payload[@"video_list"] isKindOfClass:[NSArray class]] ? payload[@"video_list"] : nil;
      if (videoList.count == 0) {
          [[KwaiParseHUD shared] dismiss];
          [self presentError:@"接口没有返回可用视频档位"];
          return;
      }

      [[KwaiParseHUD shared] dismiss];
      dispatch_async(dispatch_get_main_queue(), ^{
        [self presentQualityMenu:videoList payload:payload];
      });
    }];
    [task resume];
}

#pragma mark - UI

- (UIWindow *)keyWindow {
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

- (UIViewController *)topController {
    UIViewController *controller = [self keyWindow].rootViewController;
    while (controller) {
        if (controller.presentedViewController) {
            controller = controller.presentedViewController;
            continue;
        }
        if ([controller isKindOfClass:[UINavigationController class]]) {
            controller = ((UINavigationController *)controller).visibleViewController;
            continue;
        }
        if ([controller isKindOfClass:[UITabBarController class]]) {
            controller = ((UITabBarController *)controller).selectedViewController;
            continue;
        }
        break;
    }
    return controller;
}

- (void)presentQualityMenu:(NSArray *)videoList payload:(NSDictionary *)payload {
    UIViewController *presenter = [self topController];
    if (!presenter) {
        [[KwaiParseHUD shared] showMessage:@"无法显示解析菜单"];
        return;
    }

    NSString *title = [payload[@"title"] isKindOfClass:[NSString class]] ? payload[@"title"] : @"快手接口解析";
    if (title.length > 38) title = [[title substringToIndex:38] stringByAppendingString:@"…"];
    NSString *note = [payload[@"quality_note"] isKindOfClass:[NSString class]] ? payload[@"quality_note"] : nil;

    UIAlertController *sheet =
        [UIAlertController alertControllerWithTitle:title
                                            message:note
                                     preferredStyle:UIAlertControllerStyleActionSheet];

    for (NSDictionary *item in videoList) {
        if (![item isKindOfClass:[NSDictionary class]]) continue;
        NSString *urlString = [item[@"url"] isKindOfClass:[NSString class]] ? item[@"url"] : nil;
        NSString *level = [item[@"level"] isKindOfClass:[NSString class]] ? item[@"level"] : @"视频";
        NSString *type = [item[@"type"] isKindOfClass:[NSString class]] ? [item[@"type"] lowercaseString] : @"download";
        NSString *quality = [item[@"quality"] isKindOfClass:[NSString class]] ? item[@"quality"] : @"video";
        if (urlString.length == 0) continue;

        [sheet addAction:[UIAlertAction actionWithTitle:level
                                                 style:UIAlertActionStyleDefault
                                               handler:^(__unused UIAlertAction *action) {
          NSURL *actionURL = [NSURL URLWithString:urlString];
          if (!actionURL) {
              [[KwaiParseHUD shared] showMessage:@"视频地址无效"];
              return;
          }
          if ([type isEqualToString:@"request"]) {
              [self runRemoteAction:actionURL];
          } else {
              NSString *photoID = [payload[@"photo_id"] isKindOfClass:[NSString class]] ? payload[@"photo_id"] : @"kuaishou";
              NSString *stem = [NSString stringWithFormat:@"快手_%@_%@", photoID, quality];
              [self downloadAndSaveURL:actionURL fileStem:stem];
          }
        }]];
    }

    [sheet addAction:[UIAlertAction actionWithTitle:@"接口设置…"
                                             style:UIAlertActionStyleDefault
                                           handler:^(__unused UIAlertAction *action) {
      [self presentInterfaceSettings];
    }]];
    [sheet addAction:[UIAlertAction actionWithTitle:@"取消"
                                             style:UIAlertActionStyleCancel
                                           handler:nil]];

    UIPopoverPresentationController *popover = sheet.popoverPresentationController;
    if (popover) {
        popover.sourceView = presenter.view;
        popover.sourceRect = CGRectMake(CGRectGetMidX(presenter.view.bounds),
                                        CGRectGetMidY(presenter.view.bounds),
                                        1,
                                        1);
        popover.permittedArrowDirections = 0;
    }

    [presenter presentViewController:sheet animated:YES completion:nil];
}

- (void)presentError:(NSString *)message {
    dispatch_async(dispatch_get_main_queue(), ^{
      UIViewController *presenter = [self topController];
      if (!presenter) {
          [[KwaiParseHUD shared] showMessage:message ?: @"解析失败"];
          return;
      }

      UIAlertController *alert =
          [UIAlertController alertControllerWithTitle:@"快手解析失败"
                                              message:message ?: @"未知错误"
                                       preferredStyle:UIAlertControllerStyleAlert];
      [alert addAction:[UIAlertAction actionWithTitle:@"修改接口"
                                               style:UIAlertActionStyleDefault
                                             handler:^(__unused UIAlertAction *action) {
        [self presentInterfaceSettings];
      }]];
      [alert addAction:[UIAlertAction actionWithTitle:@"取消"
                                               style:UIAlertActionStyleCancel
                                             handler:nil]];
      [presenter presentViewController:alert animated:YES completion:nil];
    });
}

- (void)presentInterfaceSettings {
    dispatch_async(dispatch_get_main_queue(), ^{
      UIViewController *presenter = [self topController];
      if (!presenter) return;

      UIAlertController *alert =
          [UIAlertController alertControllerWithTitle:@"解析接口设置"
                                              message:@"填写完整接口前缀，插件会在末尾追加 URL 编码后的快手分享链接；也可使用 %@ 作为占位符。"
                                       preferredStyle:UIAlertControllerStyleAlert];
      [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
        NSString *saved = [NSUserDefaults.standardUserDefaults stringForKey:kKwaiParseInterfaceKey];
        field.text = saved ?: @"";
        field.placeholder = @"https://example.com/resolve?source=dyyy&url=";
        field.clearButtonMode = UITextFieldViewModeWhileEditing;
        field.autocapitalizationType = UITextAutocapitalizationTypeNone;
        field.autocorrectionType = UITextAutocorrectionTypeNo;
      }];
      [alert addAction:[UIAlertAction actionWithTitle:@"保存"
                                               style:UIAlertActionStyleDefault
                                             handler:^(__unused UIAlertAction *action) {
        NSString *value = [alert.textFields.firstObject.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (value.length == 0) {
            [NSUserDefaults.standardUserDefaults removeObjectForKey:kKwaiParseInterfaceKey];
            [[KwaiParseHUD shared] showMessage:@"已清空解析接口"];
        } else {
            [NSUserDefaults.standardUserDefaults setObject:value forKey:kKwaiParseInterfaceKey];
            [[KwaiParseHUD shared] showMessage:@"解析接口已保存"];
        }
      }]];
      [alert addAction:[UIAlertAction actionWithTitle:@"取消"
                                               style:UIAlertActionStyleCancel
                                             handler:nil]];
      [presenter presentViewController:alert animated:YES completion:nil];
    });
}

#pragma mark - Remote request action

- (void)runRemoteAction:(NSURL *)url {
    [[KwaiParseHUD shared] showStatus:@"正在执行远程任务…" progress:-1.0f];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:25.0];
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];

    [[[NSURLSession sharedSession] dataTaskWithRequest:request
                                    completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
      if (error || data.length == 0) {
          [[KwaiParseHUD shared] showMessage:error.localizedDescription ?: @"远程任务失败"];
          return;
      }

      NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
      NSDictionary *payload = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : @{};
      NSString *message = [json[@"msg"] isKindOfClass:[NSString class]] ? json[@"msg"] : @"请求完成";
      double progress = [payload[@"progress"] doubleValue];
      NSString *state = [payload[@"state"] isKindOfClass:[NSString class]] ? payload[@"state"] : nil;
      BOOL terminal = [state isEqualToString:@"completed"]
                   || [state isEqualToString:@"failed"]
                   || [state isEqualToString:@"cancelled"];

      [[KwaiParseHUD shared] showStatus:message progress:progress > 0 ? (float)progress : -1.0f];
      if (terminal) {
          dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.2 * NSEC_PER_SEC)),
                         dispatch_get_main_queue(), ^{
            [[KwaiParseHUD shared] dismiss];
          });
          return;
      }

      NSString *next = [payload[@"next_url"] isKindOfClass:[NSString class]] ? payload[@"next_url"] : nil;
      if (next.length > 0) {
          dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.9 * NSEC_PER_SEC)),
                         dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            NSURL *nextURL = [NSURL URLWithString:next];
            if (nextURL) [self runRemoteAction:nextURL];
          });
      } else {
          [[KwaiParseHUD shared] showMessage:message];
      }
    }] resume];
}

#pragma mark - Download

- (void)downloadAndSaveURL:(NSURL *)url fileStem:(NSString *)fileStem {
    @synchronized(self) {
        if (self.downloadTask) {
            [[KwaiParseHUD shared] showMessage:@"已有视频正在下载"];
            return;
        }
    }

    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.defaultSessionConfiguration;
    configuration.requestCachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
    configuration.timeoutIntervalForRequest = 30.0;
    configuration.timeoutIntervalForResource = 600.0;

    NSOperationQueue *queue = [[NSOperationQueue alloc] init];
    queue.maxConcurrentOperationCount = 1;
    self.downloadSession = [NSURLSession sessionWithConfiguration:configuration delegate:self delegateQueue:queue];
    self.downloadFileStem = [self safeFileStem:fileStem];
    self.downloadFileHandled = NO;

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    [request setValue:@"Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
   forHTTPHeaderField:@"User-Agent"];

    self.downloadTask = [self.downloadSession downloadTaskWithRequest:request];
    [[KwaiParseHUD shared] showStatus:@"快手视频下载中…" progress:0.0f];
    [self.downloadTask resume];
}

- (NSString *)safeFileStem:(NSString *)stem {
    NSString *value = stem.length > 0 ? stem : @"快手视频";
    NSCharacterSet *invalid = [NSCharacterSet characterSetWithCharactersInString:@"/\\:*?\"<>|\n\r\t"];
    NSArray *parts = [value componentsSeparatedByCharactersInSet:invalid];
    value = [parts componentsJoinedByString:@"_"];
    if (value.length > 100) value = [value substringToIndex:100];
    return value;
}

- (void)URLSession:(NSURLSession *)session
      downloadTask:(NSURLSessionDownloadTask *)downloadTask
      didWriteData:(int64_t)bytesWritten
 totalBytesWritten:(int64_t)totalBytesWritten
totalBytesExpectedToWrite:(int64_t)totalBytesExpectedToWrite {
    if (totalBytesExpectedToWrite <= 0) {
        [[KwaiParseHUD shared] showStatus:@"快手视频下载中…" progress:-1.0f];
        return;
    }
    float progress = (float)((double)totalBytesWritten / (double)totalBytesExpectedToWrite);
    NSString *status = [NSString stringWithFormat:@"快手视频下载中 · %d%%", (int)llround(progress * 100.0)];
    [[KwaiParseHUD shared] showStatus:status progress:progress];
}

- (void)URLSession:(NSURLSession *)session
      downloadTask:(NSURLSessionDownloadTask *)downloadTask
didFinishDownloadingToURL:(NSURL *)location {
    NSString *stem = self.downloadFileStem ?: @"快手视频";
    NSString *filename = [stem stringByAppendingPathExtension:@"mp4"];
    NSURL *target = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:filename]];

    NSFileManager *fm = NSFileManager.defaultManager;
    [fm removeItemAtURL:target error:nil];
    NSError *moveError = nil;
    if (![fm moveItemAtURL:location toURL:target error:&moveError]) {
        [[KwaiParseHUD shared] showMessage:moveError.localizedDescription ?: @"下载文件保存失败"];
        [self clearDownloadState];
        return;
    }

    self.downloadFileHandled = YES;
    [[KwaiParseHUD shared] showStatus:@"下载完成，正在写入相册…" progress:1.0f];
    [self saveVideoToPhotos:target];
}

- (void)URLSession:(NSURLSession *)session
              task:(NSURLSessionTask *)task
didCompleteWithError:(NSError *)error {
    if (error && !self.downloadFileHandled) {
        [[KwaiParseHUD shared] showMessage:[NSString stringWithFormat:@"下载失败\n%@", error.localizedDescription]];
        [self clearDownloadState];
    }
}

- (void)saveVideoToPhotos:(NSURL *)fileURL {
    void (^saveBlock)(void) = ^{
      [[PHPhotoLibrary sharedPhotoLibrary] performChanges:^{
        [PHAssetCreationRequest creationRequestForAssetFromVideoAtFileURL:fileURL];
      }
          completionHandler:^(BOOL success, NSError *error) {
            [[NSFileManager defaultManager] removeItemAtURL:fileURL error:nil];
            if (success) {
                [[KwaiParseHUD shared] showMessage:@"已保存到相册"];
            } else {
                [[KwaiParseHUD shared] showMessage:[NSString stringWithFormat:@"保存失败\n%@", error.localizedDescription ?: @"未知错误"]];
            }
            [self clearDownloadState];
          }];
    };

    PHAuthorizationStatus status = [PHPhotoLibrary authorizationStatusForAccessLevel:PHAccessLevelAddOnly];
    if (status == PHAuthorizationStatusAuthorized || status == PHAuthorizationStatusLimited) {
        saveBlock();
    } else if (status == PHAuthorizationStatusNotDetermined) {
        [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelAddOnly
                                                   handler:^(PHAuthorizationStatus newStatus) {
          if (newStatus == PHAuthorizationStatusAuthorized || newStatus == PHAuthorizationStatusLimited) {
              saveBlock();
          } else {
              [[KwaiParseHUD shared] showMessage:@"没有相册写入权限"];
              [self clearDownloadState];
          }
        }];
    } else {
        [[KwaiParseHUD shared] showMessage:@"没有相册写入权限"];
        [self clearDownloadState];
    }
}

- (void)clearDownloadState {
    @synchronized(self) {
        [self.downloadSession finishTasksAndInvalidate];
        self.downloadSession = nil;
        self.downloadTask = nil;
        self.downloadFileStem = nil;
        self.downloadFileHandled = NO;
    }
}

@end
