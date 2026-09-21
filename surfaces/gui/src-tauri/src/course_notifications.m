#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <UserNotifications/UserNotifications.h>
#include <stdatomic.h>
#include <stdbool.h>

@interface EdisonCourseNotificationDelegate : NSObject <UNUserNotificationCenterDelegate>
@end
@implementation EdisonCourseNotificationDelegate
- (void)userNotificationCenter:(UNUserNotificationCenter *)center
      willPresentNotification:(UNNotification *)notification
        withCompletionHandler:(void (^)(UNNotificationPresentationOptions))completion {
    completion(UNNotificationPresentationOptionBanner | UNNotificationPresentationOptionList | UNNotificationPresentationOptionSound);
}
@end

static EdisonCourseNotificationDelegate *courseDelegate;
static atomic_bool requestingPermission = false;

static UNUserNotificationCenter *center(void) {
    if (NSBundle.mainBundle.bundleIdentifier.length == 0) return nil;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        courseDelegate = [EdisonCourseNotificationDelegate new];
        UNUserNotificationCenter.currentNotificationCenter.delegate = courseDelegate;
    });
    return UNUserNotificationCenter.currentNotificationCenter;
}

// Called only by the native worker, never the main/UI thread. No future requests
// are scheduled with macOS: quitting the process therefore stops all reminders.
int edison_course_permission(void) {
    @autoreleasepool {
        UNUserNotificationCenter *notifications = center();
        if (!notifications) return -2;
        if (atomic_load(&requestingPermission)) return 10;
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        __block int status = -1;
        [notifications getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings *settings) {
            status = (int)settings.authorizationStatus;
            dispatch_semaphore_signal(done);
        }];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC))) return -1;
        return status;
    }
}

void edison_course_request_permission(void) {
    @autoreleasepool {
        UNUserNotificationCenter *notifications = center();
        if (!notifications || atomic_exchange(&requestingPermission, true)) return;
        [notifications requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionSound)
            completionHandler:^(BOOL granted, NSError *error) {
                (void)granted; (void)error;
                atomic_store(&requestingPermission, false);
            }];
    }
}

bool edison_course_notify(const char *identifier, const char *title, const char *body) {
    @autoreleasepool {
        UNUserNotificationCenter *notifications = center();
        if (!notifications) return false;
        UNMutableNotificationContent *content = [UNMutableNotificationContent new];
        content.title = [NSString stringWithUTF8String:title];
        content.body = [NSString stringWithUTF8String:body];
        content.sound = UNNotificationSound.defaultSound;
        content.threadIdentifier = @"curriculum";
        UNNotificationRequest *request = [UNNotificationRequest requestWithIdentifier:[NSString stringWithUTF8String:identifier]
            content:content trigger:nil];
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        __block bool success = false;
        [notifications addNotificationRequest:request withCompletionHandler:^(NSError *error) {
            success = error == nil;
            dispatch_semaphore_signal(done);
        }];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC))) return false;
        return success;
    }
}

// Native smoke harness uses the OS-delivered list, not just API acceptance.
int edison_course_delivered_count(void) {
    @autoreleasepool {
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        __block int count = -1;
        [center() getDeliveredNotificationsWithCompletionHandler:^(NSArray<UNNotification *> *notifications) {
            count = (int)notifications.count;
            dispatch_semaphore_signal(done);
        }];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC))) return -1;
        return count;
    }
}

// Foundation's run loop services callbacks while the isolated smoke bundle has
// no Tauri window. Production uses the application's normal event loop instead.
void edison_course_smoke_pump(void) {
    @autoreleasepool {
        static dispatch_once_t once;
        dispatch_once(&once, ^{
            [NSApplication sharedApplication];
            [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
            [NSApp finishLaunching];
            [UNUserNotificationCenter.currentNotificationCenter removeAllDeliveredNotifications];
        });
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
    }
}
