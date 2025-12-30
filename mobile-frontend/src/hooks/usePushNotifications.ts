/**
 * Push Notification Hook
 *
 * Handles Expo push notification registration and incoming notifications.
 * Registers device token with backend for Cass-initiated messages.
 */

import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { useAuthStore } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import { config } from '../config';

// Configure notification handling
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export interface PushNotificationState {
  expoPushToken: string | null;
  notification: Notifications.Notification | null;
  error: string | null;
}

export function usePushNotifications() {
  const [expoPushToken, setExpoPushToken] = useState<string | null>(null);
  const [notification, setNotification] = useState<Notifications.Notification | null>(null);
  const [error, setError] = useState<string | null>(null);

  const notificationListener = useRef<Notifications.Subscription | null>(null);
  const responseListener = useRef<Notifications.Subscription | null>(null);

  const { accessToken, user } = useAuthStore();
  const { addMessage, setCurrentConversationId } = useChatStore();

  // Register for push notifications
  const registerForPushNotifications = async (): Promise<string | null> => {
    if (!Device.isDevice) {
      setError('Push notifications require a physical device');
      return null;
    }

    try {
      // Check existing permissions
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      // Request permission if not granted
      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }

      if (finalStatus !== 'granted') {
        setError('Push notification permission denied');
        return null;
      }

      // Get Expo push token
      const projectId = Constants.expoConfig?.extra?.eas?.projectId;
      const tokenData = await Notifications.getExpoPushTokenAsync({
        projectId,
      });

      const token = tokenData.data;
      setExpoPushToken(token);

      // Configure Android notification channel
      if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('cass-messages', {
          name: 'Cass Messages',
          importance: Notifications.AndroidImportance.HIGH,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#7c3aed',
        });
      }

      return token;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get push token';
      setError(message);
      console.error('Push registration error:', err);
      return null;
    }
  };

  // Register token with backend
  const registerTokenWithBackend = async (token: string): Promise<boolean> => {
    if (!accessToken) {
      console.log('No access token, skipping push registration');
      return false;
    }

    try {
      const response = await fetch(`${config.apiBaseUrl}/push/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          token,
          platform: Platform.OS,
        }),
      });

      if (!response.ok) {
        throw new Error(`Registration failed: ${response.status}`);
      }

      const data = await response.json();
      console.log('Push token registered:', data.token_id);
      return true;
    } catch (err) {
      console.error('Failed to register push token:', err);
      return false;
    }
  };

  // Handle incoming notification while app is foregrounded
  const handleNotification = (notification: Notifications.Notification) => {
    setNotification(notification);

    const data = notification.request.content.data as {
      type?: string;
      conversation_id?: string;
      text?: string;
      timestamp?: string;
    };

    // Handle Cass-initiated messages
    if (data.type === 'cass_message') {
      addMessage({
        role: 'assistant',
        content: data.text || notification.request.content.body || '',
        timestamp: data.timestamp || new Date().toISOString(),
      });
    }
  };

  // Handle notification tap (user response)
  const handleNotificationResponse = (response: Notifications.NotificationResponse) => {
    const data = response.notification.request.content.data as {
      type?: string;
      conversation_id?: string;
    };

    // Navigate to conversation if provided
    if (data.conversation_id) {
      setCurrentConversationId(data.conversation_id);
    }
  };

  // Initialize on mount
  useEffect(() => {
    if (!config.pushEnabled) {
      return;
    }

    // Register for push notifications
    registerForPushNotifications().then((token) => {
      if (token) {
        registerTokenWithBackend(token);
      }
    });

    // Set up notification listeners
    notificationListener.current = Notifications.addNotificationReceivedListener(
      handleNotification
    );

    responseListener.current = Notifications.addNotificationResponseReceivedListener(
      handleNotificationResponse
    );

    return () => {
      if (notificationListener.current) {
        notificationListener.current.remove();
      }
      if (responseListener.current) {
        responseListener.current.remove();
      }
    };
  }, [accessToken]);

  // Re-register when user logs in
  useEffect(() => {
    if (accessToken && expoPushToken) {
      registerTokenWithBackend(expoPushToken);
    }
  }, [accessToken]);

  return {
    expoPushToken,
    notification,
    error,
    registerForPushNotifications,
  };
}
