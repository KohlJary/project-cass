/**
 * Bottom tab navigator for main app screens
 */

import React, { useCallback } from 'react';
import { Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { ChatScreen } from '../screens/ChatScreen';
import { GrowthScreen } from '../screens/GrowthScreen';
import { ProfileScreen } from '../screens/ProfileScreen';
import { colors } from '../theme/colors';

// Simple emoji icons as fallback (always works)
const TabIcon = ({ icon, color }: { icon: string; color: string }) => (
  <Text style={{ fontSize: 20, color }}>{icon}</Text>
);

const Tab = createBottomTabNavigator();

interface Props {
  userId: string;
  displayName: string;
  onLogout: () => void;
}

export function TabNavigator({
  userId,
  displayName,
  onLogout,
}: Props) {
  // Create wrapper components that capture the props
  const ChatTab = useCallback(
    () => (
      <ChatScreen
        userId={userId}
        displayName={displayName}
        onLogout={onLogout}
      />
    ),
    [userId, displayName, onLogout]
  );

  const GrowthTab = useCallback(
    () => <GrowthScreen userId={userId} />,
    [userId]
  );

  const ProfileTab = useCallback(
    () => (
      <ProfileScreen
        userId={userId}
        displayName={displayName}
        onLogout={onLogout}
      />
    ),
    [userId, displayName, onLogout]
  );

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
        },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textMuted,
      }}
    >
      <Tab.Screen
        name="Chat"
        component={ChatTab}
        options={{
          tabBarLabel: 'Chat',
          tabBarIcon: ({ color }) => <TabIcon icon="💬" color={color} />,
        }}
      />
      <Tab.Screen
        name="Growth"
        component={GrowthTab}
        options={{
          tabBarLabel: 'Growth',
          tabBarIcon: ({ color }) => <TabIcon icon="🌱" color={color} />,
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileTab}
        options={{
          tabBarLabel: 'Profile',
          tabBarIcon: ({ color }) => <TabIcon icon="👤" color={color} />,
        }}
      />
    </Tab.Navigator>
  );
}
