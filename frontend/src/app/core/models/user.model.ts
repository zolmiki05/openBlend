export interface User {
  username: string;
  platform: 'spotify' | 'apple_music';
  is_temp_password: boolean;
}

export interface AuthState {
  user: User | null;
  token: string | null;
}
